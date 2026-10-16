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
# A cold Render instance stays asleep through short /health probes. The request
# that wakes it is GET / held open for about a minute. This cap covers that
# delay and still leaves a health reserve inside the 120s startup window.
_ORIGIN_WAKE_READ_TIMEOUT = 75.0
_HEALTH_RESERVE_SECONDS = 20.0
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
    """The origin wake or the following health checks did not succeed in time."""

    def __init__(
        self,
        http_status: int | None = None,
        *,
        reason: str = "health_deadline",
        stage: str = "health",
    ) -> None:
        self.stage = stage
        self.http_status = http_status
        self.reason = reason
        super().__init__(self.public_message)

    @property
    def public_message(self) -> str:
        if self.reason == "connection_failure":
            return "Could not connect to the Backlog Agent during startup."
        if self.reason == "upstream_bad_gateway":
            return (
                "Backlog Agent kept returning HTTP 502. "
                "The process is not accepting requests."
            )
        if self.reason == "wake_timeout":
            return "Backlog Agent wake-up timed out before the service responded."
        if self.http_status is not None:
            return (
                "Backlog Agent did not become ready before the health deadline. "
                f"Last health status was HTTP {self.http_status}."
            )
        return "Backlog Agent did not become ready before the health deadline."


class BacklogUnavailableError(Exception):
    """Backlog Agent is not reachable or not healthy."""

    def __init__(self, http_status: int | None = None, stage: str = "health") -> None:
        super().__init__("backlog agent is unavailable")
        self.stage = stage
        self.http_status = http_status


class BacklogUnauthorizedError(Exception):
    """Backlog Agent rejected the bearer token."""

    def __init__(self, http_status: int | None = None, stage: str = "health") -> None:
        super().__init__("backlog agent rejected the bearer token")
        self.stage = stage
        self.http_status = http_status


class BacklogGenerationUnconfirmedError(Exception):
    """POST /generate timed out or was interrupted; the result is unknown."""

    def __init__(self) -> None:
        super().__init__("backlog generation did not return a confirmed result")
        self.stage = "generate"
        self.http_status = None


class BacklogDownstreamError(Exception):
    """The Backlog Agent returned a non-success HTTP status."""

    def __init__(self, status_code: int, stage: str = "generate") -> None:
        super().__init__("backlog agent returned an error")
        self.status_code = status_code
        self.stage = stage
        self.http_status = status_code


def reset_wake_state() -> None:
    """Clear coalesced wake state. Tests only."""

    global _probe_task, _probe_lock, _probe_started_at, _probe_attempt
    _probe_task = None
    _probe_lock = None
    _probe_started_at = None
    _probe_attempt = 0


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


def _wake_timeout(remaining: float) -> httpx.Timeout:
    """Bound one GET /health attempt. Readiness polls stay short."""

    configured = _env_float("BACKLOG_AGENT_HEALTH_TIMEOUT_SECONDS", _WAKE_READ_TIMEOUT)
    return _bounded_timeout(min(configured, _WAKE_READ_TIMEOUT), remaining)


def _origin_wake_timeout(remaining: float) -> httpx.Timeout:
    """Hold GET / long enough for Render to boot, without using the whole window.

    When the service is suspended, Render's proxy answers GET /health with 502
    and does not keep that request open through startup. GET / is held until
    the process is listening, which takes about a minute. The read budget is
    capped below the remaining startup window so /health can still be polled.
    """

    if remaining > _HEALTH_RESERVE_SECONDS + 1.0:
        read_timeout = min(_ORIGIN_WAKE_READ_TIMEOUT, remaining - _HEALTH_RESERVE_SECONDS)
    else:
        read_timeout = min(_WAKE_READ_TIMEOUT, remaining)
    return _bounded_timeout(read_timeout, remaining)


def _origin_url(url: str) -> str:
    """Service origin only. Never append /health or /generate."""

    return f"{url.rstrip('/')}/"


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


def _origin_outcome(response: httpx.Response) -> str:
    """A non-5xx origin response means the process answered. It is not readiness.

    FastAPI has no root route, so 404 is the expected awake response. 502 and
    other 5xx responses still come from the proxy and must be retried.
    """

    if response.status_code >= 500:
        return "starting"
    return "awake"


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


async def _probe_origin_once(
    url: str,
    remaining: float,
) -> dict[str, bool | str | int | float | None]:
    """GET the service origin once. This is the request that wakes Render."""

    timeout = _origin_wake_timeout(remaining)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(_origin_url(url))
    except Exception as exc:
        if isinstance(exc, httpx.TimeoutException):
            outcome = "starting"
            failure = "timeout"
        elif isinstance(exc, httpx.RequestError):
            outcome = "starting"
            failure = "connection"
        else:
            outcome = "unavailable"
            failure = "error"
        _LOG.info(
            "backlog wake outcome=%s error_type=%s",
            outcome,
            type(exc).__name__,
        )
        return _status_payload(outcome, failure=failure)

    outcome = _origin_outcome(response)
    _LOG.info(
        "backlog wake outcome=%s http_status=%s",
        outcome,
        response.status_code,
    )
    return _status_payload(outcome, http_status=response.status_code)


async def _probe_health_once(
    url: str,
    remaining: float | None = None,
) -> dict[str, bool | str | int | float | None]:
    global _probe_attempt, _probe_started_at
    _probe_attempt += 1
    attempt = _probe_attempt
    if _probe_started_at is None:
        _probe_started_at = _now()
    started = _probe_started_at
    budget = _WAKE_READ_TIMEOUT if remaining is None else remaining
    timeout = _wake_timeout(budget)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(f"{url}/health")
    except Exception as exc:
        elapsed = _now() - started
        if isinstance(exc, httpx.TimeoutException):
            outcome = "starting"
            failure = "timeout"
        elif isinstance(exc, httpx.RequestError):
            outcome = "starting"
            failure = "connection"
        else:
            outcome = "unavailable"
            failure = "error"
        _log_probe(
            attempt=attempt,
            elapsed=elapsed,
            outcome=outcome,
            error_type=type(exc).__name__,
        )
        if _probe_started_at is not None and outcome == "ready":
            _probe_started_at = None
        return _status_payload(
            outcome,
            attempt=attempt,
            elapsed_seconds=elapsed,
            failure=failure,
        )

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
    return _status_payload(
        outcome,
        attempt=attempt,
        elapsed_seconds=elapsed,
        http_status=response.status_code,
    )


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


def _raise_for_status_outcome(
    outcome: str,
    http_status: int | None = None,
) -> None:
    if outcome == "ready":
        return
    if outcome == "unauthorized":
        raise BacklogUnauthorizedError(http_status, stage="health")
    if outcome == "unavailable":
        raise BacklogUnavailableError(http_status, stage="health")
    raise BacklogNotReadyError(http_status)


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
    """Wake the origin with GET /, then poll GET /health until it is ready.

    POST /generate is not issued here. A 5xx from either request is not readiness.
    """

    deadline = _now() + startup_timeout

    async def _attempt(phase: str, probe) -> dict[str, bool | str | int | float | None]:
        remaining = deadline - _now()
        if remaining <= 0:
            raise BacklogNotReadyError(
                reason="wake_timeout" if phase == "wake" else "health_deadline",
                stage="wake" if phase == "wake" else "health",
            )
        return await probe(url, remaining)

    def _give_up(
        phase: str,
        *,
        last_http_status: int | None,
        timeouts: int,
        connections: int,
        statuses: list[int],
    ) -> None:
        raise BacklogNotReadyError(
            last_http_status,
            reason=_failure_reason(
                phase=phase,
                timeouts=timeouts,
                connections=connections,
                statuses=statuses,
            ),
            stage="wake" if phase == "wake" else "health",
        )

    async def _poll_until(phase: str, probe, success: str) -> None:
        delay = _WAKE_DELAY_SECONDS
        last_http_status: int | None = None
        timeouts = 0
        connections = 0
        statuses: list[int] = []
        while True:
            result = await _attempt(phase, probe)
            outcome = str(result["status"])
            failure = result.get("failure")
            last_http_status = _http_status_of(result)
            if failure == "timeout":
                timeouts += 1
            elif failure == "connection":
                connections += 1
            elif last_http_status is not None and outcome != success:
                statuses.append(last_http_status)
            if outcome == success:
                return
            if outcome in {"unauthorized", "unavailable"}:
                _raise_for_status_outcome(outcome, last_http_status)
            remaining = deadline - _now()
            if remaining <= 0:
                _give_up(
                    phase,
                    last_http_status=last_http_status,
                    timeouts=timeouts,
                    connections=connections,
                    statuses=statuses,
                )
            await asyncio.sleep(min(delay, remaining))
            delay = min(_WAKE_DELAY_MAX_SECONDS, delay + 0.5)
            if _now() >= deadline:
                _give_up(
                    phase,
                    last_http_status=last_http_status,
                    timeouts=timeouts,
                    connections=connections,
                    statuses=statuses,
                )

    await _poll_until("wake", _probe_origin_once, "awake")
    await _poll_until("health", _probe_health_once, "ready")


async def generate_backlog(envelope: dict[str, Any]) -> dict[str, Any]:
    """Wake GET /, wait for GET /health, then POST the envelope exactly once."""

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
        raise BacklogGenerationUnconfirmedError from None

    if response.status_code in _AUTH_HTTP:
        raise BacklogUnauthorizedError(response.status_code, stage="generate")
    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            raise BacklogDownstreamError(502) from None
        if (
            isinstance(payload, dict)
            and "backlog" in payload
            and "findings" in payload
        ):
            return payload
        raise BacklogDownstreamError(502)
    raise BacklogDownstreamError(response.status_code)
