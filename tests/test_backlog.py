import asyncio
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import get_provider
from app.backlog_client import backlog_status, reset_wake_state
from app.main import app
from app.providers import MockProvider
from tests.test_phase0 import COMPLETE_REQUEST

app.dependency_overrides[get_provider] = MockProvider
client = TestClient(app)

COMPLETE_ENVELOPE = {
    "status": "COMPLETE",
    "workflow_status": "COMPLETE",
    "user_request": "Build a self-service portal for enterprise customers.",
}

SUCCESS_PAYLOAD = {
    "backlog": {"epics": [{"id": "E-01", "title": "Portal access"}]},
    "findings": [{"code": "INFO", "message": "ok"}],
}

AGENT_URL = "https://backlog.example.test"
AGENT_TOKEN = "secret-token-do-not-leak"


def _response(status_code: int, payload: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload if payload is not None else {"status": "error"},
        request=httpx.Request("GET", f"{AGENT_URL}/health"),
    )


def _ok_health() -> httpx.Response:
    return _response(200, {"status": "ok", "service": "backlog-agent"})


class _Delayed:
    def __init__(self, seconds: float, response: httpx.Response) -> None:
        self.seconds = seconds
        self.response = response


@pytest.fixture(autouse=True)
def _reset_wake_state():
    reset_wake_state()
    yield
    reset_wake_state()


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("BACKLOG_AGENT_URL", AGENT_URL)
    monkeypatch.setenv("BACKLOG_API_TOKEN", AGENT_TOKEN)
    monkeypatch.setenv("BACKLOG_AGENT_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("BACKLOG_AGENT_HEALTH_TIMEOUT_SECONDS", "5")


def _assert_status(response, status: str, *, available: bool) -> dict:
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == status
    assert data["available"] is available
    assert AGENT_TOKEN not in response.text
    assert "Authorization" not in response.text
    return data


def _patch_http(monkeypatch, script: list, *, hold_get=None):
    calls: list[dict] = []
    clock = {"t": 0.0}
    clients: list[dict] = []

    gets_started = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            clients.append(
                {
                    "timeout": kwargs.get("timeout"),
                    "follow_redirects": kwargs.get("follow_redirects"),
                }
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def _next(self, method: str, url: str, json=None, headers=None):
            calls.append(
                {
                    "method": method,
                    "url": url,
                    "json": json,
                    "headers": headers,
                }
            )
            if not script:
                raise AssertionError(f"unexpected {method} {url}")
            item = script.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        async def get(self, url, **kwargs):
            gets_started["n"] += 1
            if hold_get is not None:
                await hold_get.wait()
            if script and isinstance(script[0], _Delayed):
                item = script.pop(0)
                calls.append({"method": "GET", "url": url, "json": None, "headers": None})
                clock["t"] += item.seconds
                if isinstance(item.response, BaseException):
                    raise item.response
                return item.response
            return self._next("GET", url)

        async def post(self, url, json=None, headers=None, **kwargs):
            return self._next("POST", url, json=json, headers=headers)

    def _monotonic() -> float:
        return clock["t"]

    async def _sleep(seconds: float):
        clock["t"] += max(0.0, float(seconds))

    monkeypatch.setattr("app.backlog_client.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.backlog_client.asyncio.sleep", _sleep)
    monkeypatch.setattr("app.backlog_client.time.monotonic", _monotonic)
    return calls, clients, clock, gets_started


def test_backlog_status_ready(monkeypatch):
    _configure(monkeypatch)
    calls, clients, _clock, _started = _patch_http(monkeypatch, [_ok_health()])

    response = client.get("/backlog/status")

    _assert_status(response, "ready", available=True)
    assert [call["method"] for call in calls] == ["GET"]
    assert calls[0]["url"].endswith("/health")
    assert all(call["method"] != "POST" for call in calls)
    timeout = clients[0]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 30.0
    assert timeout.connect == 30.0
    assert clients[0]["follow_redirects"] is True


def test_backlog_status_starting_on_timeout(monkeypatch):
    _configure(monkeypatch)
    _patch_http(monkeypatch, [httpx.TimeoutException("timed out")])

    response = client.get("/backlog/status")

    _assert_status(response, "starting", available=False)


def test_backlog_status_starting_on_connection_error(monkeypatch):
    _configure(monkeypatch)
    _patch_http(monkeypatch, [httpx.ConnectError("connection refused")])

    response = client.get("/backlog/status")

    _assert_status(response, "starting", available=False)


def test_backlog_status_starting_on_transient_http(monkeypatch):
    _configure(monkeypatch)
    _patch_http(monkeypatch, [_response(503, {"status": "error"})])

    response = client.get("/backlog/status")

    _assert_status(response, "starting", available=False)


def test_backlog_status_unavailable_on_permanent_http(monkeypatch):
    _configure(monkeypatch)
    _patch_http(monkeypatch, [_response(404, {"detail": "not found"})])

    response = client.get("/backlog/status")

    _assert_status(response, "unavailable", available=False)


def test_backlog_status_unauthorized(monkeypatch):
    _configure(monkeypatch)
    _patch_http(monkeypatch, [_response(401, {"detail": "unauthorized"})])

    response = client.get("/backlog/status")

    _assert_status(response, "unauthorized", available=False)


def test_backlog_status_not_configured(monkeypatch):
    monkeypatch.delenv("BACKLOG_AGENT_URL", raising=False)
    monkeypatch.delenv("BACKLOG_API_TOKEN", raising=False)
    calls, _clients, _clock, _started = _patch_http(monkeypatch, [])

    response = client.get("/backlog/status")

    _assert_status(response, "not_configured", available=False)
    assert calls == []


def test_backlog_status_invalid_url(monkeypatch):
    monkeypatch.setenv("BACKLOG_AGENT_URL", "not-a-url")
    monkeypatch.setenv("BACKLOG_API_TOKEN", AGENT_TOKEN)
    calls, _clients, _clock, _started = _patch_http(monkeypatch, [])

    response = client.get("/backlog/status")

    _assert_status(response, "invalid_url", available=False)
    assert calls == []


def test_backlog_status_does_not_wait_the_startup_window(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "180")
    calls, _clients, clock, _started = _patch_http(monkeypatch, [httpx.ConnectError("connection refused")])

    response = client.get("/backlog/status")

    _assert_status(response, "starting", available=False)
    assert len(calls) == 1
    assert clock["t"] == 0.0


def test_backlog_status_does_not_leak_token(monkeypatch, caplog):
    _configure(monkeypatch)
    caplog.set_level(logging.INFO)
    _patch_http(monkeypatch, [_ok_health()])

    response = client.get("/backlog/status")

    assert AGENT_TOKEN not in response.text
    assert AGENT_TOKEN not in caplog.text
    assert "Authorization" not in caplog.text
    assert "Bearer" not in caplog.text
    assert any("backlog health attempt=" in record.getMessage() for record in caplog.records)


def test_backlog_complete_health_then_single_generate(monkeypatch):
    _configure(monkeypatch)
    calls, clients, _clock, _started = _patch_http(
        monkeypatch,
        [_ok_health(), _response(200, SUCCESS_PAYLOAD)],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 200
    assert response.json() == SUCCESS_PAYLOAD
    assert [call["method"] for call in calls] == ["GET", "POST"]
    assert [call["url"] for call in calls] == [
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/generate",
    ]
    assert calls[1]["json"] == COMPLETE_ENVELOPE
    assert calls[1]["headers"]["Authorization"] == f"Bearer {AGENT_TOKEN}"
    assert calls[0].get("headers") in (None, {})
    wake_timeout = clients[0]["timeout"]
    assert isinstance(wake_timeout, httpx.Timeout)
    assert wake_timeout.read == 30.0
    assert clients[0]["follow_redirects"] is True
    body = response.text
    assert AGENT_TOKEN not in body
    assert "Authorization" not in body


def test_sleeping_service_becomes_ready_after_transient_status_probes(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [
            httpx.ConnectError("connection refused"),
            _response(502, {"status": "error"}),
            httpx.TimeoutException("timed out"),
            _ok_health(),
            _ok_health(),
            _response(200, SUCCESS_PAYLOAD),
        ],
    )

    first = client.get("/backlog/status")
    second = client.get("/backlog/status")
    third = client.get("/backlog/status")
    ready = client.get("/backlog/status")
    generated = client.post("/backlog", json=COMPLETE_ENVELOPE)

    _assert_status(first, "starting", available=False)
    _assert_status(second, "starting", available=False)
    _assert_status(third, "starting", available=False)
    _assert_status(ready, "ready", available=True)
    assert generated.status_code == 200
    assert generated.json() == SUCCESS_PAYLOAD
    assert [call["method"] for call in calls] == ["GET", "GET", "GET", "GET", "GET", "POST"]
    assert calls[4]["url"] == f"{AGENT_URL}/health"
    assert calls[5]["url"] == f"{AGENT_URL}/generate"
    assert sum(1 for call in calls if call["method"] == "POST") == 1


def test_generate_wakes_sleeping_service_then_posts_once(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, clock, _started = _patch_http(
        monkeypatch,
        [
            httpx.ConnectError("connection refused"),
            _response(503, {"status": "starting"}),
            httpx.TimeoutException("timed out"),
            _ok_health(),
            _response(200, SUCCESS_PAYLOAD),
        ],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 200
    assert response.json() == SUCCESS_PAYLOAD
    assert [call["method"] for call in calls] == ["GET", "GET", "GET", "GET", "POST"]
    assert all(call["url"] == f"{AGENT_URL}/health" for call in calls[:-1])
    assert calls[-2]["url"] == f"{AGENT_URL}/health"
    assert calls[-1]["url"] == f"{AGENT_URL}/generate"
    assert calls[-1]["json"] == COMPLETE_ENVELOPE
    assert clock["t"] >= 2.0
    assert clock["t"] <= 9.0
    assert sum(1 for call in calls if call["url"].endswith("/generate")) == 1


def test_generate_cold_start_timeout_does_not_post(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "2.5")
    calls, _clients, clock, _started = _patch_http(
        monkeypatch,
        [
            httpx.TimeoutException("timed out"),
            httpx.ConnectError("connection refused"),
            httpx.TimeoutException("timed out"),
        ],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "BACKLOG_STARTING"
    assert data["stage"] == "health"
    assert data["reason"] == "health_deadline"
    assert "health deadline" in data["message"]
    assert data["elapsed_seconds"] >= 2.0
    assert AGENT_TOKEN not in response.text
    assert all(call["url"] == f"{AGENT_URL}/health" for call in calls)
    assert all(not call["url"].endswith("/generate") for call in calls)
    assert len([call for call in calls if call["method"] == "GET"]) >= 2
    assert clock["t"] >= 2.0


def test_repeated_502_then_ready_posts_generate_once(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, clock, _started = _patch_http(
        monkeypatch,
        [
            _response(502, {"status": "error"}),
            _response(502, {"status": "error"}),
            _ok_health(),
            _response(200, SUCCESS_PAYLOAD),
        ],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 200
    assert response.json() == SUCCESS_PAYLOAD
    assert [call["url"] for call in calls] == [
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/generate",
    ]
    assert calls[-1]["json"] == COMPLETE_ENVELOPE
    assert clock["t"] >= 2.0
    assert sum(1 for call in calls if call["method"] == "POST") == 1
    assert calls[-1]["headers"]["Authorization"] == f"Bearer {AGENT_TOKEN}"
    health_timeouts = [client_info["timeout"] for client_info in _clients]
    assert all(isinstance(item, httpx.Timeout) and item.read == 30.0 for item in health_timeouts[:-1])


def test_timeouts_then_ready_posts_generate_once(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [
            httpx.ReadTimeout("timed out"),
            httpx.ConnectTimeout("timed out"),
            _ok_health(),
            _response(200, SUCCESS_PAYLOAD),
        ],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 200
    assert [call["url"] for call in calls] == [
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/generate",
    ]
    assert sum(1 for call in calls if call["url"].endswith("/generate")) == 1


def test_persistent_502_is_not_reported_as_a_generic_startup_timeout(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "2.5")
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [_response(502, {"status": "error"}) for _ in range(6)],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "BACKLOG_STARTING"
    assert data["stage"] == "health"
    assert data["reason"] == "upstream_bad_gateway"
    assert data["http_status"] == 502
    assert "HTTP 502" in data["message"]
    assert "health deadline" not in data["message"]
    assert data["elapsed_seconds"] >= 2.0
    assert "Elapsed" in data["message"]
    assert AGENT_TOKEN not in response.text
    assert all(call["method"] == "GET" and call["url"] == f"{AGENT_URL}/health" for call in calls)


def test_connection_failures_are_distinct_from_upstream_502(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "2.5")
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [httpx.ConnectError("connection refused") for _ in range(6)],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    data = response.json()
    assert response.status_code == 503
    assert data["reason"] == "connection_failure"
    assert data["stage"] == "health"
    assert all(call["url"] == f"{AGENT_URL}/health" for call in calls)
    assert data["elapsed_seconds"] >= 2.0
    assert "http_status" not in data
    assert "connect" in data["message"].lower()
    assert all(not call["url"].endswith("/generate") for call in calls)


def test_health_read_timeout_cannot_consume_the_startup_window(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BACKLOG_AGENT_HEALTH_TIMEOUT_SECONDS", "75")
    _calls, clients, _clock, _started = _patch_http(monkeypatch, [_ok_health()])

    response = client.get("/backlog/status")

    assert response.status_code == 200
    timeout = clients[0]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 30.0
    assert timeout.connect == 30.0


@pytest.mark.parametrize(
    "raw_url",
    [
        AGENT_URL,
        f"{AGENT_URL}/",
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/health/",
        f"{AGENT_URL}/generate",
        f"{AGENT_URL}/generate/",
    ],
)
def test_generate_normalizes_origin_health_and_generate(monkeypatch, raw_url):
    monkeypatch.setenv("BACKLOG_AGENT_URL", raw_url)
    monkeypatch.setenv("BACKLOG_API_TOKEN", AGENT_TOKEN)
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "120")
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [_ok_health(), _response(200, SUCCESS_PAYLOAD)],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 200
    assert [call["url"] for call in calls] == [
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/generate",
    ]
    assert calls[-1]["json"] == COMPLETE_ENVELOPE
    assert sum(1 for call in calls if call["url"].endswith("/generate")) == 1


def test_wake_health_timeout_then_later_poll_posts_generate_once(monkeypatch):
    _configure(monkeypatch)
    calls, clients, _clock, _started = _patch_http(
        monkeypatch,
        [
            httpx.ReadTimeout("timed out"),
            _ok_health(),
            _response(200, SUCCESS_PAYLOAD),
        ],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 200
    assert response.json() == SUCCESS_PAYLOAD
    assert [call["url"] for call in calls] == [
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/generate",
    ]
    wake_timeout = clients[0]["timeout"]
    poll_timeout = clients[1]["timeout"]
    assert isinstance(wake_timeout, httpx.Timeout)
    assert isinstance(poll_timeout, httpx.Timeout)
    assert wake_timeout.read == 30.0
    assert poll_timeout.read == 30.0
    assert sum(1 for call in calls if call["method"] == "POST") == 1
    assert calls[-1]["json"] == COMPLETE_ENVELOPE


def test_ready_service_is_polled_before_one_generate(monkeypatch):
    _configure(monkeypatch)
    calls, clients, clock, _started = _patch_http(
        monkeypatch,
        [_ok_health(), _response(200, SUCCESS_PAYLOAD)],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 200
    assert [call["url"] for call in calls] == [
        f"{AGENT_URL}/health",
        f"{AGENT_URL}/generate",
    ]
    assert clock["t"] == 0.0
    assert isinstance(clients[0]["timeout"], httpx.Timeout)
    assert clients[0]["timeout"].read == 30.0
    assert sum(1 for call in calls if call["method"] == "POST") == 1


def test_health_deadline_is_distinct_from_wake_timeout(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "2.5")
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [
            _response(502, {"status": "error"}),
            httpx.TimeoutException("timed out"),
            httpx.TimeoutException("timed out"),
            httpx.TimeoutException("timed out"),
        ],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    data = response.json()
    assert response.status_code == 503
    assert data["reason"] == "health_deadline"
    assert data["stage"] == "health"
    assert "health deadline" in data["message"]
    assert data["elapsed_seconds"] >= 2.0
    assert calls[0]["url"] == f"{AGENT_URL}/health"
    assert all(call["url"] == f"{AGENT_URL}/health" for call in calls)
    assert all(call["method"] != "POST" for call in calls)


def test_wake_request_that_uses_the_startup_window_does_not_poll(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "5")
    calls, clients, clock, _started = _patch_http(
        monkeypatch,
        [_Delayed(5, httpx.ReadTimeout("timed out"))],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    data = response.json()
    assert response.status_code == 503
    assert data["reason"] == "wake_timeout"
    assert data["stage"] == "wake"
    assert "wake-up timed out" in data["message"]
    assert data["elapsed_seconds"] >= 5.0
    assert clock["t"] == 5.0
    assert [call["url"] for call in calls] == [f"{AGENT_URL}/health"]
    assert isinstance(clients[0]["timeout"], httpx.Timeout)
    assert clients[0]["timeout"].read == 5.0


def test_concurrent_status_probes_share_one_health_request(monkeypatch):
    _configure(monkeypatch)
    probes = []

    async def _probe(url: str, remaining: float | None = None, *, wake: bool = False):
        probes.append((url, remaining, wake))
        await asyncio.sleep(0.02)
        return {
            "available": True,
            "status": "ready",
            "attempt": 1,
            "elapsed_seconds": 0.02,
        }

    monkeypatch.setattr("app.backlog_client._probe_health_once", _probe)

    async def _run():
        return await asyncio.gather(backlog_status(), backlog_status())

    results = asyncio.run(_run())
    assert [item["status"] for item in results] == ["ready", "ready"]
    assert probes == [(AGENT_URL, 30.0, True)]


def test_backlog_missing_configuration(monkeypatch):
    monkeypatch.delenv("BACKLOG_AGENT_URL", raising=False)
    monkeypatch.setenv("BACKLOG_API_TOKEN", AGENT_TOKEN)
    calls, _clients, _clock, _started = _patch_http(monkeypatch, [])

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "BACKLOG_NOT_CONFIGURED"
    assert AGENT_TOKEN not in response.text
    assert calls == []


def test_backlog_rejects_needs_info(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(monkeypatch, [])
    envelope = dict(COMPLETE_ENVELOPE)
    envelope["status"] = "NEEDS_INFO"
    envelope["workflow_status"] = "NEEDS_INFO"

    response = client.post("/backlog", json=envelope)

    assert response.status_code == 422
    assert response.json()["error"] == "INCOMPLETE_WORKFLOW"
    assert calls == []


def test_backlog_rejects_blocked(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(monkeypatch, [])
    envelope = dict(COMPLETE_ENVELOPE)
    envelope["status"] = "BLOCKED"
    envelope["workflow_status"] = "BLOCKED"

    response = client.post("/backlog", json=envelope)

    assert response.status_code == 422
    assert response.json()["error"] == "INCOMPLETE_WORKFLOW"
    assert calls == []


def test_backlog_rejects_missing_statuses(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(monkeypatch, [])

    response = client.post("/backlog", json={"user_request": "portal"})

    assert response.status_code == 422
    assert response.json()["error"] == "INCOMPLETE_WORKFLOW"
    assert calls == []


def test_backlog_rejects_mismatched_statuses(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(monkeypatch, [])
    envelope = dict(COMPLETE_ENVELOPE)
    envelope["workflow_status"] = "NEEDS_INFO"

    response = client.post("/backlog", json=envelope)

    assert response.status_code == 422
    assert response.json()["error"] == "INCOMPLETE_WORKFLOW"
    assert calls == []


def test_backlog_health_timeout_does_not_generate(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BACKLOG_AGENT_STARTUP_TIMEOUT_SECONDS", "0.05")
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [httpx.TimeoutException("timed out"), httpx.TimeoutException("timed out")],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 503
    assert response.json()["error"] == "BACKLOG_STARTING"
    assert all(call["method"] != "POST" for call in calls)
    assert all(not call["url"].endswith("/generate") for call in calls)


def test_backlog_downstream_error(monkeypatch):
    _configure(monkeypatch)
    _patch_http(monkeypatch, [_ok_health(), _response(500, {"detail": "boom"})])

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 502
    data = response.json()
    assert data["error"] == "BACKLOG_DOWNSTREAM_ERROR"
    assert "boom" not in response.text
    assert AGENT_URL not in response.text
    assert AGENT_TOKEN not in response.text


def test_backlog_downstream_validation_error(monkeypatch):
    _configure(monkeypatch)
    _patch_http(
        monkeypatch,
        [_ok_health(), _response(422, {"detail": "bad envelope"})],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 422
    assert response.json()["error"] == "BACKLOG_REJECTED"
    assert "bad envelope" not in response.text


def test_backlog_generation_timeout_is_unconfirmed(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [_ok_health(), httpx.TimeoutException("timed out")],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 504
    data = response.json()
    assert data["error"] == "BACKLOG_GENERATION_UNCONFIRMED"
    assert "unknown" in data["message"].lower()
    assert "generation failed" not in data["message"].lower()
    assert [call["method"] for call in calls] == ["GET", "POST"]
    assert calls[-1]["url"] == f"{AGENT_URL}/generate"


def test_backlog_unauthorized_generate(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [_ok_health(), _response(401, {"detail": "bad token"})],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "BACKLOG_UNAUTHORIZED"
    assert "bad token" not in response.text
    assert AGENT_TOKEN not in response.text
    assert [call["method"] for call in calls] == ["GET", "POST"]
    assert calls[-1]["url"] == f"{AGENT_URL}/generate"


def test_backlog_unauthorized_health_does_not_generate(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [_response(403, {"detail": "forbidden"})],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "BACKLOG_UNAUTHORIZED"
    assert data["stage"] == "wake"
    assert data["http_status"] == 403
    assert "elapsed_seconds" in data
    assert "forbidden" not in response.text
    assert [call["url"] for call in calls] == [f"{AGENT_URL}/health"]
    assert all(call["method"] != "POST" for call in calls)


def test_backlog_permanent_health_error_does_not_generate(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [_response(404, {"detail": "missing"})],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "BACKLOG_UNAVAILABLE"
    assert data["stage"] == "wake"
    assert data["http_status"] == 404
    assert data["elapsed_seconds"] >= 0
    assert "HTTP 404" in data["message"]
    assert "non-transient" in data["message"]
    assert "missing" not in response.text
    assert [call["url"] for call in calls] == [f"{AGENT_URL}/health"]
    assert all(call["method"] != "POST" for call in calls)


def test_backlog_does_not_retry_generation(monkeypatch):
    _configure(monkeypatch)
    calls, _clients, _clock, _started = _patch_http(
        monkeypatch,
        [_ok_health(), httpx.ConnectError("interrupted")],
    )

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 504
    assert response.json()["error"] == "BACKLOG_GENERATION_UNCONFIRMED"
    post_calls = [call for call in calls if call["method"] == "POST"]
    assert len(post_calls) == 1


def test_backlog_invalid_url_generate(monkeypatch):
    monkeypatch.setenv("BACKLOG_AGENT_URL", "ftp://example.test")
    monkeypatch.setenv("BACKLOG_API_TOKEN", AGENT_TOKEN)
    calls, _clients, _clock, _started = _patch_http(monkeypatch, [])

    response = client.post("/backlog", json=COMPLETE_ENVELOPE)

    assert response.status_code == 503
    assert response.json()["error"] == "BACKLOG_INVALID_URL"
    assert calls == []


def test_analyze_does_not_invoke_backlog_generation(monkeypatch):
    called = []

    async def forbidden(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("analyze must not generate a backlog")

    monkeypatch.setattr("app.api.generate_backlog", forbidden)

    response = client.post(
        "/analyze",
        json={"user_request": COMPLETE_REQUEST},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETE"
    assert called == []
