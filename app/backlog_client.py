"""HTTP client for the standalone Backlog Agent. Never imports that package."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

_LOG = logging.getLogger("app.backlog_client")

_DEFAULT_GENERATE_TIMEOUT = 300.0
_DEFAULT_STARTUP_TIMEOUT = 120.0
_WAKE_CONNECT_TIMEOUT = 5.0
_WAKE_READ_TIMEOUT = 5.0
_WAKE_WRITE_TIMEOUT = 5.0
_WAKE_POOL_TIMEOUT = 5.0
# Same budget as Invoke-RestMethod -TimeoutSec 30 against GET /health.
_WAKE_REQUEST_TIMEOUT = 30.0
_WAKE_DELAY_SECONDS = 2.0
_WAKE_DELAY_MAX_SECONDS = 3.0
_TRANSIENT_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
_AUTH_HTTP = frozenset({401, 403})
_REDIRECT_HTTP = frozenset({301, 302, 303, 307, 308})

_probe_task: asyncio.Task | None = None
_probe_lock: asyncio.Lock | None = None
_probe_started_at: float | None = None
_probe_attempt = 0


def _now() -> float:
    return time.monotonic()


class BacklogConfigError(Exception):
    """URL or API token is missing."""


class BacklogInvalidUrlError(Exception):
    """BACKLOG_AGENT_URL is not a usable http(s) origin."""


class BacklogNotReadyError(Exception):
    """The wake-up request or the following health checks did not succeed in time."""

    def __init__(
        self,
        http_status: int | None = None,
        *,
        reason: str = "health_deadline",
        stage: str = "health",
        elapsed_seconds: float | None = None,
        detail: str | None = None,
    ) -> None:
        self.stage = stage
        self.http_status = http_status
        self.reason = reason
        self.elapsed_seconds = elapsed_seconds
        self.detail = detail
        super().__init__(self.public_message)

    @property
    def public_message(self) -> str:
        if self.reason == "connection_failure":
            message = "Could not connect to the Backlog Agent during startup."
        elif self.reason == "upstream_bad_gateway":
            message = (
                "Backlog Agent kept returning HTTP 502. "
                "The process is not accepting requests."
            )
        elif self.reason == "wake_timeout":
            message = "Backlog Agent wake-up timed out before the service responded."
        elif self.http_status is not None:
            message = (
                "Backlog Agent did not become ready before the health deadline. "
                f"Last health status was HTTP {self.http_status}."
            )
        else:
            message = "Backlog Agent did not become ready before the health deadline."
        return _with_error_context(message, self.elapsed_seconds, self.detail)


class BacklogUnavailableError(Exception):
    """Backlog Agent returned a non-transient HTTP error."""

    def __init__(
        self,
        http_status: int | None = None,
        stage: str = "health",
        *,
        elapsed_seconds: float | None = None,
        detail: str | None = None,
    ) -> None:
        self.stage = stage
        self.http_status = http_status
        self.elapsed_seconds = elapsed_seconds
        self.detail = detail
        super().__init__(self.public_message)

    @property
    def public_message(self) -> str:
        status = f" HTTP {self.http_status}." if self.http_status is not None else "."
        return _with_error_context(
            f"Backlog Agent returned a non-transient error during {self.stage}.{status}",
            self.elapsed_seconds,
            self.detail,
        )


class BacklogUnauthorizedError(Exception):
    """Backlog Agent rejected the bearer token."""

    def __init__(
        self,
        http_status: int | None = None,
        stage: str = "health",
        *,
        elapsed_seconds: float | None = None,
        detail: str | None = None,
    ) -> None:
        self.stage = stage
        self.http_status = http_status
        self.elapsed_seconds = elapsed_seconds
        self.detail = detail
        super().__init__(self.public_message)

    @property
    def public_message(self) -> str:
        status = f" HTTP {self.http_status}." if self.http_status is not None else "."
        return _with_error_context(
            f"Backlog Agent authentication failed during {self.stage}.{status}",
            self.elapsed_seconds,
            self.detail,
        )


class BacklogGenerationUnconfirmedError(Exception):
    """POST /generate timed out or was interrupted; the result is unknown."""

    def __init__(
        self,
        *,
        elapsed_seconds: float | None = None,
        detail: str | None = None,
    ) -> None:
        self.stage = "generate"
        self.http_status = None
        self.elapsed_seconds = elapsed_seconds
        self.detail = detail or "POST /generate did not return a response. The result is unknown."
        super().__init__(self.public_message)

    @property
    def public_message(self) -> str:
        return _with_error_context(
            "Backlog generation did not return a confirmed result. The outcome is unknown.",
            self.elapsed_seconds,
            self.detail,
        )


class BacklogDownstreamError(Exception):
    """The Backlog Agent returned a non-success HTTP status."""

    def __init__(
        self,
        status_code: int,
        stage: str = "generate",
        *,
        elapsed_seconds: float | None = None,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.stage = stage
        self.http_status = status_code
        self.elapsed_seconds = elapsed_seconds
        self.detail = detail or f"POST /generate returned HTTP {status_code}."
        super().__init__(self.public_message)

    @property
    def public_message(self) -> str:
        if self.status_code == 422:
            message = "Backlog Agent rejected the request."
        else:
            message = "Backlog Agent returned an error."
        return _with_error_context(message, self.elapsed_seconds, self.detail)


def reset_wake_state() -> None:
    """Clear coalesced wake state. Tests only."""

    global _probe_task, _probe_lock, _probe_started_at, _probe_attempt
    _probe_task = None
    _probe_lock = None
    _probe_started_at = None
    _probe_attempt = 0


def _with_error_context(
    message: str,
    elapsed_seconds: float | None,
    detail: str | None,
) -> str:
    parts = [message.strip()]
    if detail and detail.strip() and detail.strip() not in parts[0]:
        parts.append(detail.strip())
    if elapsed_seconds is not None:
        parts.append(f"Elapsed {max(0.0, elapsed_seconds):.1f}s.")
    return " ".join(parts)


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _normalized_agent_url(raw: str) -> str | None:
    url = raw.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
        return None
    path = parsed.path.rstrip("/")
    for suffix in ("/health", "/generate"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")


def _settings() -> tuple[str, str, float, float]:
    raw_url = (os.getenv("BACKLOG_AGENT_URL") or "").strip()
    token = (os.getenv("BACKLOG_API_TOKEN") or "").strip()
    generate_timeout = _env_float("BACKLOG_AGENT_TIMEOUT_SECONDS", _DEFAULT_GENERATE_TIMEOUT)
    startup_timeout = _env_float(
        "BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", _DEFAULT_STARTUP_TIMEOUT
    )
    if not raw_url or not token:
        raise BacklogConfigError
    url = _normalized_agent_url(raw_url)
    if url is None:
        raise BacklogInvalidUrlError
    return url, token, generate_timeout, startup_timeout


def _bounded_timeout(read_timeout: float, remaining: float) -> httpx.Timeout:
    read = min(max(read_timeout, 0.001), remaining)
    connect = min(_WAKE_CONNECT_TIMEOUT, remaining)
    return httpx.Timeout(
        connect=max(connect, 0.001),
        read=max(read, 0.001),
        write=max(min(_WAKE_WRITE_TIMEOUT, remaining), 0.001),
        pool=max(min(_WAKE_POOL_TIMEOUT, remaining), 0.001),
    )


def _poll_timeout(remaining: float) -> httpx.Timeout:
    """Bound one readiness poll. These stay short; the wake request does not."""

    configured = _env_float("BACKLOG_AGENT_HEALTH_TIMEOUT_SECONDS", _WAKE_READ_TIMEOUT)
    return _bounded_timeout(min(configured, _WAKE_READ_TIMEOUT), remaining)


def _wake_request_timeout(remaining: float) -> httpx.Timeout:
    """One GET /health budget, matching a 30-second Invoke-RestMethod timeout.

    The budget is capped by the time still left in the startup window so a
    single wake request cannot run past the readiness deadline.
    """

    budget = min(_WAKE_REQUEST_TIMEOUT, max(remaining, 0.001))
    return httpx.Timeout(budget)


def _health_is_ready(response: httpx.Response) -> bool:
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    return str(payload.get("status") or "").strip().lower() in {"ok", "ready"}


def _status_payload(
    status: str,
    *,
    attempt: int = 0,
    elapsed_seconds: float = 0.0,
    http_status: int | None = None,
    failure: str | None = None,
) -> dict[str, bool | str | int | float | None]:
    payload: dict[str, bool | str | int | float | None] = {
        "available": status == "ready",
        "status": status,
        "attempt": attempt,
        "elapsed_seconds": round(max(0.0, elapsed_seconds), 3),
    }
    if http_status is not None:
        payload["http_status"] = http_status
    if failure is not None:
        payload["failure"] = failure
    return payload


def _classify_health_response(response: httpx.Response) -> str:
    if _health_is_ready(response):
        return "ready"
    code = response.status_code
    if code in _AUTH_HTTP:
        return "unauthorized"
    if code in _TRANSIENT_HTTP or code in _REDIRECT_HTTP:
        return "starting"
    return "unavailable"


def _safe_health_detail(response: httpx.Response) -> str:
    """Describe a health response without copying an arbitrary body."""

    marker = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        status = str(payload.get("status") or "").strip().lower()
        if status in {"ok", "ready", "error", "starting"}:
            marker = f" Body status {status}."
    return f"GET /health returned HTTP {response.status_code}.{marker}"


def _log_probe(
    *,
    attempt: int,
    elapsed: float,
    outcome: str,
    http_status: int | None = None,
    error_type: str | None = None,
) -> None:
    _LOG.info(
        "backlog health attempt=%s elapsed_s=%.3f outcome=%s http_status=%s error_type=%s",
        attempt,
        elapsed,
        outcome,
        http_status if http_status is not None else "-",
        error_type or "-",
    )


async def _probe_health_once(
    url: str,
    remaining: float | None = None,
    *,
    wake: bool = False,
) -> dict[str, bool | str | int | float | None]:
    """GET /health once.

    ``wake=True`` is the explicit cold-start request: a 30-second timeout, the
    same call as ``Invoke-RestMethod .../health -TimeoutSec 30``. Readiness
    polls stay on the short health timeout.
    """

    global _probe_attempt, _probe_started_at
    _probe_attempt += 1
    attempt = _probe_attempt
    if _probe_started_at is None:
        _probe_started_at = _now()
    started = _probe_started_at
    budget = _WAKE_READ_TIMEOUT if remaining is None else remaining
    timeout = _wake_request_timeout(budget) if wake else _poll_timeout(budget)
    phase = "wake" if wake else "health"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await asyncio.wait_for(
                client.get(f"{url}/health"),
                timeout=timeout.read or budget,
            )
    except Exception as exc:
        elapsed = _now() - started
        if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            outcome = "starting"
            failure = "timeout"
            detail = f"GET /health timed out during {phase}."
        elif isinstance(exc, httpx.RequestError):
            outcome = "starting"
            failure = "connection"
            detail = f"GET /health could not connect during {phase}."
        else:
            outcome = "unavailable"
            failure = "error"
            detail = f"GET /health failed during {phase}."
        _LOG.info(
            "backlog %s attempt=%s elapsed_s=%.3f outcome=%s error_type=%s",
            phase,
            attempt,
            elapsed,
            outcome,
            type(exc).__name__,
        )
        payload = _status_payload(
            outcome,
            attempt=attempt,
            elapsed_seconds=elapsed,
            failure=failure,
        )
        payload["detail"] = detail
        return payload

    elapsed = _now() - started
    outcome = _classify_health_response(response)
    _log_probe(
        attempt=attempt,
        elapsed=elapsed,
        outcome=outcome,
        http_status=response.status_code,
    )
    if outcome == "ready":
        _probe_started_at = None
        _probe_attempt = 0
    payload = _status_payload(
        outcome,
        attempt=attempt,
        elapsed_seconds=elapsed,
        http_status=response.status_code,
    )
    if outcome != "ready":
        payload["detail"] = _safe_health_detail(response)
    return payload


async def _coalesced_probe(url: str) -> dict[str, bool | str | int | float]:
    """One in-flight GET /health shared by overlapping status/generate calls."""

    global _probe_task, _probe_lock
    if _probe_lock is None:
        _probe_lock = asyncio.Lock()
    async with _probe_lock:
        current = _probe_task
        if current is None or current.done():
            current = asyncio.get_running_loop().create_task(_probe_health_once(url))
            _probe_task = current
    return await current


async def backlog_status() -> dict[str, bool | str | int | float]:
    """Start or join one long health probe. Does not loop for the startup window."""

    try:
        url, _token, _generate_timeout, _startup_timeout = _settings()
    except BacklogConfigError:
        return _status_payload("not_configured")
    except BacklogInvalidUrlError:
        return _status_payload("invalid_url")

    return await _coalesced_probe(url)


def _http_status_of(health: dict[str, bool | str | int | float | None]) -> int | None:
    value = health.get("http_status")
    return value if isinstance(value, int) else None


def _detail_of(health: dict[str, bool | str | int | float | None]) -> str | None:
    detail = health.get("detail")
    text = str(detail or "").strip()
    return text or None


def _raise_terminal_health(
    outcome: str,
    *,
    stage: str,
    http_status: int | None,
    elapsed_seconds: float,
    detail: str | None,
) -> None:
    if outcome == "unauthorized":
        raise BacklogUnauthorizedError(
            http_status,
            stage=stage,
            elapsed_seconds=elapsed_seconds,
            detail=detail,
        )
    if outcome == "unavailable":
        raise BacklogUnavailableError(
            http_status,
            stage=stage,
            elapsed_seconds=elapsed_seconds,
            detail=detail,
        )


def _failure_reason(
    *,
    phase: str,
    timeouts: int,
    connections: int,
    statuses: list[int],
) -> str:
    observed = timeouts + connections + len(statuses)
    if observed and timeouts == 0 and not statuses and connections == observed:
        return "connection_failure"
    if timeouts == 0 and connections == 0 and statuses and set(statuses) == {502}:
        return "upstream_bad_gateway"
    if phase == "wake":
        return "wake_timeout"
    return "health_deadline"


async def _await_backlog_ready(url: str, startup_timeout: float) -> None:
    """Wake with one 30s GET /health, then poll GET /health until it is ready.

    A wake-up timeout or transient HTTP error is recoverable. POST /generate
    is not issued here. A non-transient status stops the wait immediately.
    """

    started = _now()
    deadline = started + startup_timeout
    delay = _WAKE_DELAY_SECONDS
    last_http_status: int | None = None
    last_detail: str | None = None
    timeouts = 0
    connections = 0
    statuses: list[int] = []
    woke = False

    def elapsed() -> float:
        return max(0.0, _now() - started)

    def give_up(phase: str) -> None:
        raise BacklogNotReadyError(
            last_http_status,
            reason=_failure_reason(
                phase=phase,
                timeouts=timeouts,
                connections=connections,
                statuses=statuses,
            ),
            stage=phase,
            elapsed_seconds=elapsed(),
            detail=last_detail,
        )

    def observe(result: dict[str, bool | str | int | float | None]) -> str:
        nonlocal last_http_status, last_detail, timeouts, connections
        outcome = str(result["status"])
        failure = result.get("failure")
        last_http_status = _http_status_of(result)
        last_detail = _detail_of(result)
        if failure == "timeout":
            timeouts += 1
        elif failure == "connection":
            connections += 1
        elif last_http_status is not None and outcome != "ready":
            statuses.append(last_http_status)
        return outcome

    remaining = deadline - _now()
    if remaining <= 0:
        give_up("wake")
    wake = await _probe_health_once(url, remaining, wake=True)
    outcome = observe(wake)
    if outcome in {"unauthorized", "unavailable"}:
        _raise_terminal_health(
            outcome,
            stage="wake",
            http_status=last_http_status,
            elapsed_seconds=elapsed(),
            detail=last_detail,
        )
    if _now() >= deadline:
        give_up("wake")
    woke = True

    while True:
        remaining = deadline - _now()
        if remaining <= 0:
            give_up("health" if woke else "wake")
        result = await _probe_health_once(url, remaining, wake=False)
        outcome = observe(result)
        if outcome == "ready":
            return
        if outcome in {"unauthorized", "unavailable"}:
            _raise_terminal_health(
                outcome,
                stage="health",
                http_status=last_http_status,
                elapsed_seconds=elapsed(),
                detail=last_detail,
            )
        remaining = deadline - _now()
        if remaining <= 0:
            give_up("health")
        await asyncio.sleep(min(delay, remaining))
        delay = min(_WAKE_DELAY_MAX_SECONDS, delay + 0.5)
        if _now() >= deadline:
            give_up("health")


async def generate_backlog(envelope: dict[str, Any]) -> dict[str, Any]:
    """Wake GET /health, poll until ready, then POST the envelope exactly once."""

    started = _now()
    url, token, generate_timeout, startup_timeout = _settings()
    await _await_backlog_ready(url, startup_timeout)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=generate_timeout, follow_redirects=True) as client:
            response = await client.post(f"{url}/generate", json=envelope, headers=headers)
    except (httpx.TimeoutException, httpx.RequestError):
        _LOG.info("backlog generation did not return a confirmed result")
        raise BacklogGenerationUnconfirmedError(
            elapsed_seconds=max(0.0, _now() - started),
        ) from None

    elapsed = max(0.0, _now() - started)
    if response.status_code in _AUTH_HTTP:
        raise BacklogUnauthorizedError(
            response.status_code,
            stage="generate",
            elapsed_seconds=elapsed,
            detail=f"POST /generate returned HTTP {response.status_code}.",
        )
    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            raise BacklogDownstreamError(502, elapsed_seconds=elapsed) from None
        if (
            isinstance(payload, dict)
            and "backlog" in payload
            and "findings" in payload
        ):
            return payload
        raise BacklogDownstreamError(502, elapsed_seconds=elapsed)
    raise BacklogDownstreamError(response.status_code, elapsed_seconds=elapsed)
