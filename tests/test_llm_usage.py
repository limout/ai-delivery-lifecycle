from types import SimpleNamespace

from app.api import _InstrumentedProvider
from app.providers import (
    AIProvider,
    map_gemini_usage,
    map_mock_usage,
    map_ollama_usage,
    map_openrouter_usage,
)


USAGE_KEYS = {
    "provider",
    "model",
    "node",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "duration_ms",
}


def test_gemini_usage_mapping_from_object():
    meta = SimpleNamespace(
        prompt_token_count=12,
        candidates_token_count=34,
        total_token_count=46,
    )
    usage = map_gemini_usage(meta, "gemini-3.5-flash-lite", 250)
    assert set(usage) == USAGE_KEYS
    assert usage["provider"] == "gemini"
    assert usage["model"] == "gemini-3.5-flash-lite"
    assert usage["node"] is None
    assert usage["input_tokens"] == 12
    assert usage["output_tokens"] == 34
    assert usage["total_tokens"] == 46
    assert usage["duration_ms"] == 250
    assert "prompt_token_count" not in usage
    assert "candidates_token_count" not in usage


def test_gemini_usage_mapping_from_dict_and_derived_total():
    usage = map_gemini_usage(
        {"prompt_token_count": 10, "candidates_token_count": 5},
        "gemini-test",
        80,
    )
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 5
    assert usage["total_tokens"] == 15


def test_openrouter_usage_mapping():
    usage = map_openrouter_usage(
        {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
        "openrouter/free",
        100,
    )
    assert set(usage) == USAGE_KEYS
    assert usage["provider"] == "openrouter"
    assert usage["input_tokens"] == 20
    assert usage["output_tokens"] == 7
    assert usage["total_tokens"] == 27
    assert "prompt_tokens" not in usage
    assert "completion_tokens" not in usage


def test_openrouter_usage_mapping_derived_total():
    usage = map_openrouter_usage(
        {"prompt_tokens": 8, "completion_tokens": 2},
        "openrouter/free",
        10,
    )
    assert usage["total_tokens"] == 10


def test_ollama_usage_mapping_prompt_eval_and_eval_count():
    usage = map_ollama_usage(
        {
            "response": "{}",
            "prompt_eval_count": 26,
            "eval_count": 298,
        },
        "qwen3:8b",
        400,
    )
    assert set(usage) == USAGE_KEYS
    assert usage["provider"] == "ollama"
    assert usage["model"] == "qwen3:8b"
    assert usage["input_tokens"] == 26
    assert usage["output_tokens"] == 298
    assert usage["total_tokens"] == 324
    assert "prompt_eval_count" not in usage
    assert "eval_count" not in usage


def test_missing_usage_metadata_maps_to_none_tokens():
    gemini = map_gemini_usage(None, "gemini-test", 15)
    openrouter = map_openrouter_usage(None, "openrouter/free", 15)
    ollama = map_ollama_usage({}, "qwen3:8b", 15)

    for usage in (gemini, openrouter, ollama):
        assert usage["input_tokens"] is None
        assert usage["output_tokens"] is None
        assert usage["total_tokens"] is None
        assert usage["duration_ms"] == 15


def test_mock_usage_is_safe_zeros():
    usage = map_mock_usage("mock", 3)
    assert usage["provider"] == "mock"
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["total_tokens"] == 0
    assert usage["duration_ms"] == 3


class _StubProvider(AIProvider):
    def __init__(self, last_usage: dict | None):
        self.last_usage = last_usage

    def generate_json(self, prompt: str, schema: dict) -> dict:
        return {"ok": True, "prompt": prompt, "schema": schema}


class _NoUsageProvider(AIProvider):
    def generate_json(self, prompt: str, schema: dict) -> dict:
        return {"ok": True}


def test_instrumented_provider_collects_normalized_usage():
    inner = _StubProvider(
        {
            "provider": "openrouter",
            "model": "openrouter/free",
            "node": None,
            "input_tokens": 4,
            "output_tokens": 6,
            "total_tokens": 10,
            "duration_ms": 90,
        }
    )
    instrumented = _InstrumentedProvider(inner)
    instrumented.current_node = "discovery"
    result = instrumented.generate_json("hello", {"required": ["problem"]})

    assert result["ok"] is True
    assert instrumented.llm_calls == 1
    assert len(instrumented.llm_usage) == 1
    record = instrumented.llm_usage[0]
    assert set(record) == USAGE_KEYS
    assert record["provider"] == "openrouter"
    assert record["model"] == "openrouter/free"
    assert record["node"] == "discovery"
    assert record["input_tokens"] == 4
    assert record["output_tokens"] == 6
    assert record["total_tokens"] == 10
    assert record["duration_ms"] == 90


def test_instrumented_provider_missing_inner_usage_is_safe():
    instrumented = _InstrumentedProvider(_NoUsageProvider())
    instrumented.current_node = "validation"
    instrumented.generate_json("prompt", {})

    record = instrumented.llm_usage[0]
    assert record["node"] == "validation"
    assert record["input_tokens"] is None
    assert record["output_tokens"] is None
    assert record["total_tokens"] is None
    assert isinstance(record["duration_ms"], int)
    assert record["duration_ms"] >= 0


def test_instrumented_provider_attributes_each_call_to_current_node():
    inner = _StubProvider(
        {
            "provider": "gemini",
            "model": "gemini-test",
            "node": None,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "duration_ms": 1,
        }
    )
    instrumented = _InstrumentedProvider(inner)
    instrumented.current_node = "discovery"
    instrumented.generate_json("one", {})
    instrumented.current_node = "requirements"
    instrumented.generate_json("two", {})
    instrumented.generate_json("three", {})

    nodes = [item["node"] for item in instrumented.llm_usage]
    assert nodes == ["discovery", "requirements", "requirements"]
    assert instrumented.llm_calls == 3
