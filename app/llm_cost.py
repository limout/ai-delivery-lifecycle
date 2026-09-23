"""Provider-agnostic estimated LLM cost from normalized usage records.

Pricing lives here, not in provider implementations. Cost is USD per 1M tokens.
This layer does not invent token counts or borrow another model's rates.
"""

LLM_PRICING = {
    ("gemini", "gemini-3.5-flash-lite"): {
        "input_per_1m": 0.30,
        "output_per_1m": 2.50,
    },
}


def lookup_llm_pricing(provider, model) -> dict | None:
    if provider is None or model is None:
        return None
    provider_key = str(provider).strip().lower()
    model_key = str(model).strip()
    if not provider_key or not model_key:
        return None
    rates = LLM_PRICING.get((provider_key, model_key))
    if rates is not None:
        return rates
    return LLM_PRICING.get((provider_key, model_key.lower()))


def _optional_token_count(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_cost(record: dict) -> dict:
    rates = lookup_llm_pricing(record.get("provider"), record.get("model"))
    input_tokens = _optional_token_count(record.get("input_tokens"))
    output_tokens = _optional_token_count(record.get("output_tokens"))
    if rates is None:
        return {
            "priced": False,
            "reason": "unknown_pricing",
            "input_cost_usd": None,
            "output_cost_usd": None,
            "total_cost_usd": None,
        }
    if input_tokens is None or output_tokens is None:
        return {
            "priced": False,
            "reason": "missing_tokens",
            "input_cost_usd": None,
            "output_cost_usd": None,
            "total_cost_usd": None,
        }
    input_cost = input_tokens * rates["input_per_1m"] / 1_000_000
    output_cost = output_tokens * rates["output_per_1m"] / 1_000_000
    return {
        "priced": True,
        "reason": None,
        "input_cost_usd": input_cost,
        "output_cost_usd": output_cost,
        "total_cost_usd": input_cost + output_cost,
    }


def calculate_llm_cost(usage_records) -> dict:
    records = list(usage_records or [])
    node_order: list[str | None] = []
    by_node: dict[str | None, dict] = {}
    priced_calls = 0
    unpriced_calls = 0
    input_total = 0.0
    output_total = 0.0

    for record in records:
        if not isinstance(record, dict):
            record = {}
        node = record.get("node")
        if node not in by_node:
            node_order.append(node)
            by_node[node] = {
                "calls": 0,
                "priced_calls": 0,
                "unpriced_calls": 0,
                "input_cost_usd": 0.0,
                "output_cost_usd": 0.0,
            }
        bucket = by_node[node]
        bucket["calls"] += 1
        cost = _record_cost(record)
        if cost["priced"]:
            priced_calls += 1
            bucket["priced_calls"] += 1
            input_total += cost["input_cost_usd"]
            output_total += cost["output_cost_usd"]
            bucket["input_cost_usd"] += cost["input_cost_usd"]
            bucket["output_cost_usd"] += cost["output_cost_usd"]
        else:
            unpriced_calls += 1
            bucket["unpriced_calls"] += 1

    fully_priced = unpriced_calls == 0
    node_rows = []
    for node in node_order:
        bucket = by_node[node]
        node_priced = bucket["unpriced_calls"] == 0
        node_rows.append(
            {
                "node": node,
                "calls": bucket["calls"],
                "pricing_available": node_priced,
                "input_cost_usd": (
                    bucket["input_cost_usd"] if node_priced else None
                ),
                "output_cost_usd": (
                    bucket["output_cost_usd"] if node_priced else None
                ),
                "total_cost_usd": (
                    bucket["input_cost_usd"] + bucket["output_cost_usd"]
                    if node_priced
                    else None
                ),
            }
        )

    return {
        "pricing_available": fully_priced,
        "calls": len(records),
        "priced_calls": priced_calls,
        "unpriced_calls": unpriced_calls,
        "input_cost_usd": input_total if fully_priced else None,
        "output_cost_usd": output_total if fully_priced else None,
        "total_cost_usd": (input_total + output_total) if fully_priced else None,
        "by_node": node_rows,
    }


def _usd_6(value) -> str | None:
    if value is None:
        return None
    try:
        return f"${float(value):.6f}"
    except (TypeError, ValueError):
        return None


def format_llm_cost_log_lines(llm_cost) -> list[str]:
    """Readable [COST] lines from an existing calculate_llm_cost() result."""
    cost = llm_cost if isinstance(llm_cost, dict) else {}
    unavailable = "[COST] unavailable: pricing missing for one or more LLM calls"
    if not cost.get("pricing_available"):
        return [unavailable]

    total = _usd_6(cost.get("total_cost_usd"))
    input_cost = _usd_6(cost.get("input_cost_usd"))
    output_cost = _usd_6(cost.get("output_cost_usd"))
    calls = cost.get("calls")
    if total is None or input_cost is None or output_cost is None:
        return [unavailable]

    lines = [
        f"[COST] total={total} input={input_cost} output={output_cost} "
        f"calls={calls}"
    ]
    for row in cost.get("by_node") or []:
        if not isinstance(row, dict):
            continue
        node_total = _usd_6(row.get("total_cost_usd"))
        if node_total is None:
            continue
        node = row.get("node") or "unknown"
        lines.append(f"[COST] {node}={node_total}")
    return lines


def log_llm_cost(llm_cost) -> None:
    for line in format_llm_cost_log_lines(llm_cost):
        print(line)
