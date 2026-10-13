"""HTTP client for the standalone Backlog Agent. Never imports that package."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

_LOG = logging.getLogger("app.backlog_client")

_DEFAULT_GENERATE_TIMEOUT = 300.0
_DEFAULT_STARTUP_TIMEOUT = 90.0
_STATUS_HEALTH_TIMEOUT = 5.0
_POLL_HEALTH_TIMEOUT = 5.0
_POLL_INTERVAL_SECONDS = 1.0
_TRANSIENT_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
_AUTH_HTTP = frozenset({401, 403})


class BacklogConfigError(Exception):
    """URL or API token is missing."""


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


def _settings() -> tuple[str, str, float, float]:
    url = (os.getenv("BACKLOG_AGENT_URL") or "").strip().rstrip("/")
    token = (os.getenv("BACKLOG_API_TOKEN") or "").strip()
    generate_timeout = _env_float("BACKLOG_AGENT_TIMEOUT_SECONDS", _DEFAULT_GENERATE_TIMEOUT)
    startup_timeout = _env_float(
        "BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", _DEFAULT_STARTUP_TIMEOUT
    )
    if not url or not token:
        raise BacklogConfigError
    return url, token, generate_timeout, startup_timeout


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


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


def _status_payload(status: str) -> dict[str, bool | str]:
    return {"available": status == "ready", "status": status}


def _classify_health_response(response: httpx.Response) -> str:
    if _health_is_ready(response):
        return "ready"
    code = response.status_code
    if code in _AUTH_HTTP:
        return "unauthorized"
    if code in _TRANSIENT_HTTP:
        return "starting"
    return "unavailable"


def _classify_health_exception(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        _LOG.info("backlog health check timed out")
        return "starting"
    if isinstance(exc, httpx.RequestError):
        _LOG.info("backlog health check could not connect")
        return "starting"
    return "unavailable"


async def backlog_status() -> dict[str, bool | str]:
    """One short health check. Does not wait for the startup timeout."""

    try:
        url, _token, _generate_timeout, _startup_timeout = _settings()
    except BacklogConfigError:
        return _status_payload("not_configured")

    try:
        async with httpx.AsyncClient(timeout=_STATUS_HEALTH_TIMEOUT) as client:
            response = await client.get(f"{url}/health")
    except Exception as exc:
        return _status_payload(_classify_health_exception(exc))

    return _status_payload(_classify_health_response(response))


async def _wait_until_ready(url: str, startup_timeout: float) -> None:
    deadline = time.monotonic() + startup_timeout
    last = "starting"
    attempted = False
    while True:
        remaining = deadline - time.monotonic()
        if attempted and remaining <= 0:
            break
        attempted = True
        timeout = min(_POLL_HEALTH_TIMEOUT, max(0.1, remaining if remaining > 0 else 0.1))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{url}/health")
            last = _classify_health_response(response)
            if last == "ready":
                return
            if last == "unauthorized":
                raise BacklogUnauthorizedError
            if last == "unavailable":
                raise BacklogUnavailableError
        except BacklogUnauthorizedError:
            raise
        except BacklogUnavailableError:
            raise
        except httpx.TimeoutException:
            last = "starting"
        except httpx.RequestError:
            last = "starting"
        sleep_for = min(_POLL_INTERVAL_SECONDS, max(0.0, deadline - time.monotonic()))
        if sleep_for <= 0:
            break
        await asyncio.sleep(sleep_for)
    if last == "starting":
        raise BacklogNotReadyError
    raise BacklogUnavailableError


async def generate_backlog(envelope: dict[str, Any]) -> dict[str, Any]:
    """Poll health, then POST /generate exactly once. Never retries generation."""

    url, token, generate_timeout, startup_timeout = _settings()
    await _wait_until_ready(url, startup_timeout)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=generate_timeout) as client:
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
