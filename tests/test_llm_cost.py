import pytest

from app.api import _execution_payload
from app.llm_cost import calculate_llm_cost, format_llm_cost_log_lines


GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"
APPROX = {"rel": 1e-9, "abs": 1e-12}


def _usage(
    *,
    node="discovery",
    provider="gemini",
    model=GEMINI_FLASH_LITE,
    input_tokens=10,
    output_tokens=4,
    total_tokens=None,
):
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "provider": provider,
        "model": model,
        "node": node,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "duration_ms": 1,
    }


def test_gemini_flash_lite_pricing():
    result = calculate_llm_cost(
        [_usage(input_tokens=1_000_000, output_tokens=1_000_000)]
    )
    assert result["pricing_available"] is True
    assert result["input_cost_usd"] == 0.30
    assert result["output_cost_usd"] == 2.50
    assert result["total_cost_usd"] == 2.80


def test_multiple_usage_records_aggregate():
    records = [
        _usage(node="discovery", input_tokens=1000, output_tokens=200),
        _usage(node="requirements", input_tokens=3000, output_tokens=400),
    ]
    result = calculate_llm_cost(records)
    assert result["calls"] == 2
    assert result["pricing_available"] is True
    assert result["input_cost_usd"] == pytest.approx(
        4000 * 0.30 / 1_000_000, **APPROX
    )
    assert result["output_cost_usd"] == pytest.approx(
        600 * 2.50 / 1_000_000, **APPROX
    )
    assert result["total_cost_usd"] == pytest.approx(
        result["input_cost_usd"] + result["output_cost_usd"], **APPROX
    )


def test_per_node_attribution():
    records = [
        _usage(node="discovery", input_tokens=690, output_tokens=322),
        _usage(node="requirements", input_tokens=100, output_tokens=50),
        _usage(node="requirements", input_tokens=200, output_tokens=25),
    ]
    result = calculate_llm_cost(records)
    by_node = {item["node"]: item for item in result["by_node"]}
    assert [item["node"] for item in result["by_node"]] == [
        "discovery",
        "requirements",
    ]
    assert by_node["discovery"]["calls"] == 1
    assert by_node["requirements"]["calls"] == 2
    assert by_node["discovery"]["input_cost_usd"] == pytest.approx(
        690 * 0.30 / 1_000_000, **APPROX
    )
    assert by_node["discovery"]["output_cost_usd"] == pytest.approx(
        322 * 2.50 / 1_000_000, **APPROX
    )
    assert by_node["requirements"]["total_cost_usd"] == pytest.approx(
        (300 * 0.30 + 75 * 2.50) / 1_000_000, **APPROX
    )


def test_missing_token_metadata_does_not_crash():
    result = calculate_llm_cost(
        [_usage(input_tokens=None, output_tokens=None, total_tokens=None)]
    )
    assert result["pricing_available"] is False
    assert result["input_cost_usd"] is None
    assert result["output_cost_usd"] is None
    assert result["total_cost_usd"] is None
    assert result["unpriced_calls"] == 1
    assert result["by_node"][0]["pricing_available"] is False
    assert result["by_node"][0]["total_cost_usd"] is None


def test_unknown_provider_model_is_unpriced():
    result = calculate_llm_cost(
        [_usage(provider="ollama", model="qwen3:8b", input_tokens=100, output_tokens=20)]
    )
    assert result["pricing_available"] is False
    assert result["total_cost_usd"] is None
    assert result["unpriced_calls"] == 1
    assert result["by_node"][0]["pricing_available"] is False


def test_zero_token_records_cost_zero():
    result = calculate_llm_cost(
        [_usage(input_tokens=0, output_tokens=0, total_tokens=0)]
    )
    assert result["pricing_available"] is True
    assert result["input_cost_usd"] == 0.0
    assert result["output_cost_usd"] == 0.0
    assert result["total_cost_usd"] == 0.0


def test_real_nine_call_gemini_totals():
    records = [
        _usage(node=f"call_{index}", input_tokens=0, output_tokens=0)
        for index in range(8)
    ]
    records.append(
        _usage(node="estimate", input_tokens=11084, output_tokens=3256)
    )
    result = calculate_llm_cost(records)
    assert result["calls"] == 9
    assert result["pricing_available"] is True
    assert result["input_cost_usd"] == pytest.approx(0.0033252, **APPROX)
    assert result["output_cost_usd"] == pytest.approx(0.0081400, **APPROX)
    assert result["total_cost_usd"] == pytest.approx(0.0114652, **APPROX)


def test_cost_log_for_fully_priced_run():
    records = [
        _usage(node="discovery", input_tokens=690, output_tokens=322),
        _usage(node="requirements", input_tokens=100, output_tokens=50),
    ]
    cost = calculate_llm_cost(records)
    lines = format_llm_cost_log_lines(cost)
    assert lines[0] == (
        f"[COST] total=${cost['total_cost_usd']:.6f} "
        f"input=${cost['input_cost_usd']:.6f} "
        f"output=${cost['output_cost_usd']:.6f} "
        f"calls=2"
    )
    assert lines[1] == f"[COST] discovery=${cost['by_node'][0]['total_cost_usd']:.6f}"
    assert lines[2] == f"[COST] requirements=${cost['by_node'][1]['total_cost_usd']:.6f}"
    assert cost["pricing_available"] is True


def test_cost_log_when_pricing_unavailable():
    cost = calculate_llm_cost(
        [_usage(provider="ollama", model="qwen3:8b", input_tokens=10, output_tokens=4)]
    )
    assert cost["pricing_available"] is False
    assert cost["total_cost_usd"] is None
    assert format_llm_cost_log_lines(cost) == [
        "[COST] unavailable: pricing missing for one or more LLM calls"
    ]


def test_cost_log_does_not_change_llm_cost_values():
    records = [_usage(input_tokens=11084, output_tokens=3256)]
    cost = calculate_llm_cost(records)
    before = {
        "total_cost_usd": cost["total_cost_usd"],
        "input_cost_usd": cost["input_cost_usd"],
        "output_cost_usd": cost["output_cost_usd"],
        "calls": cost["calls"],
        "by_node": [dict(item) for item in cost["by_node"]],
    }
    lines = format_llm_cost_log_lines(cost)
    assert cost["total_cost_usd"] == before["total_cost_usd"]
    assert cost["input_cost_usd"] == before["input_cost_usd"]
    assert cost["output_cost_usd"] == before["output_cost_usd"]
    assert cost["calls"] == before["calls"]
    assert cost["by_node"] == before["by_node"]
    assert lines[0] == "[COST] total=$0.011465 input=$0.003325 output=$0.008140 calls=1"


def test_execution_payload_adds_cost_without_mutating_usage():
    usage = [
        _usage(node="discovery", input_tokens=10, output_tokens=4),
    ]
    original = [dict(item) for item in usage]
    payload = _execution_payload({}, ["discovery"], 1, 1.23, "analyze", usage)
    assert payload["llm_usage"] == original
    assert "llm_cost" in payload
    assert payload["llm_cost"]["calls"] == 1
    assert payload["llm_cost"]["pricing_available"] is True
    assert set(payload["llm_usage"][0]) == set(original[0])
