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
_DEFAULT_STARTUP_TIMEOUT = 180.0
_WAKE_CONNECT_TIMEOUT = 20.0
_WAKE_READ_TIMEOUT = 75.0
_WAKE_WRITE_TIMEOUT = 15.0
_WAKE_POOL_TIMEOUT = 15.0
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
    """Health checks did not become ready within the startup window."""


class BacklogUnavailableError(Exception):
    """Backlog Agent is not reachable or not healthy."""


class BacklogUnauthorizedError(Exception):
    """Backlog Agent rejected the bearer token."""


class BacklogGenerationUnconfirmedError(Exception):
    """POST /generate timed out or was interrupted; the result is unknown."""


class BacklogDownstreamError(Exception):
    """The Backlog Agent returned a non-success HTTP status."""

    def __init__(self, status_code: int) -> None:
        super().__init__("backlog agent returned an error")
        self.status_code = status_code


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
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


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


def _wake_timeout() -> httpx.Timeout:
    """Hold the health request long enough for Render to boot the instance.

    A sleeping Free service accepts the proxy connection, then produces no
    response until the process is up. Aborting that wait (a 5s timeout) cancels
    the request that would have started the service; a browser load succeeds
    because it waits. Connect is bounded separately from the read wait.
    """

    read_timeout = _env_float("BACKLOG_AGENT_HEALTH_TIMEOUT_SECONDS", _WAKE_READ_TIMEOUT)
    return httpx.Timeout(
        connect=_WAKE_CONNECT_TIMEOUT,
        read=read_timeout,
        write=_WAKE_WRITE_TIMEOUT,
        pool=_WAKE_POOL_TIMEOUT,
    )


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
) -> dict[str, bool | str | int | float]:
    return {
        "available": status == "ready",
        "status": status,
        "attempt": attempt,
        "elapsed_seconds": round(max(0.0, elapsed_seconds), 3),
    }


def _classify_health_response(response: httpx.Response) -> str:
    if _health_is_ready(response):
        return "ready"
    code = response.status_code
    if code in _AUTH_HTTP:
        return "unauthorized"
    if code in _TRANSIENT_HTTP or code in _REDIRECT_HTTP:
        return "starting"
    return "unavailable"


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


async def _probe_health_once(url: str) -> dict[str, bool | str | int | float]:
    global _probe_attempt, _probe_started_at
    _probe_attempt += 1
    attempt = _probe_attempt
    if _probe_started_at is None:
        _probe_started_at = _now()
    started = _probe_started_at
    timeout = _wake_timeout()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(f"{url}/health")
    except Exception as exc:
        elapsed = _now() - started
        if isinstance(exc, (httpx.TimeoutException, httpx.RequestError)):
            outcome = "starting"
        else:
            outcome = "unavailable"
        _log_probe(
            attempt=attempt,
            elapsed=elapsed,
            outcome=outcome,
            error_type=type(exc).__name__,
        )
        if _probe_started_at is not None and outcome == "ready":
            _probe_started_at = None
        return _status_payload(outcome, attempt=attempt, elapsed_seconds=elapsed)

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
    return _status_payload(outcome, attempt=attempt, elapsed_seconds=elapsed)


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


def _raise_for_status_outcome(outcome: str) -> None:
    if outcome == "ready":
        return
    if outcome == "unauthorized":
        raise BacklogUnauthorizedError
    if outcome == "unavailable":
        raise BacklogUnavailableError
    raise BacklogNotReadyError


async def generate_backlog(envelope: dict[str, Any]) -> dict[str, Any]:
    """Confirm health with one coalesced probe, then POST /generate exactly once."""

    url, token, generate_timeout, _startup_timeout = _settings()
    health = await _coalesced_probe(url)
    _raise_for_status_outcome(str(health["status"]))
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
        raise BacklogUnauthorizedError
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
