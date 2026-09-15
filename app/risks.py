"""Normalize and rank delivery risks so the assessment shows distinct causes."""

from __future__ import annotations

import re


_CLUSTERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("deadline", "Deadline compression", (
        "deadline", "timeline", "schedule", "timebox", "too short",
        "missing the date", "miss the date", "will miss", "fixed date",
        "delivery date", "not enough time",
    )),
    ("integration", "Integration uncertainty", (
        "integrat", "api", "salesforce", "source of truth", "legacy system",
        "third-party", "third party", "interface",
    )),
    ("scope", "Undefined or unstable scope", (
        "scope", "mvp", "first release", "requirement", "in-scope",
        "out of scope", "unclear function",
    )),
    ("migration", "Data migration complexity", (
        "migrat", "data volume", "legacy data", "cutover", "records",
    )),
    ("compliance", "Security or compliance constraint", (
        "security", "compliance", "regulat", "privacy", "gdpr", "hipaa", "audit",
    )),
    ("capacity", "Capacity or staffing risk", (
        "resource", "capacity", "staffing", "team size", "availability",
    )),
    ("quality", "Acceptance or quality risk", (
        "test", "quality", "acceptance", "defect", "regression",
    )),
    ("dependency", "External dependency", (
        "dependenc", "vendor", "third party approval", "access not",
        "awaiting",
    )),
)


def _cluster_for(text: str) -> tuple[str, str]:
    lower = text.lower()
    for code, title, markers in _CLUSTERS:
        if any(marker in lower for marker in markers):
            return code, title
    return "other", text.strip()[:80] or "Delivery risk"


def _impact(cluster: str, text: str, deadline_fit: str) -> int:
    lower = text.lower()
    score = 1
    if cluster == "deadline" or deadline_fit == "EXCEEDS":
        score += 3
    if cluster in {"integration", "scope", "migration"}:
        score += 2
    if cluster in {"compliance", "capacity"}:
        score += 1
    if any(word in lower for word in ("high", "critical", "block", "miss")):
        score += 1
    return score


def normalize_delivery_risks(
    items: list | None,
    *,
    deadline_fit: str = "",
    evidence: str = "",
    limit: int = 5,
) -> list[str]:
    """Group similar risks and return 3–5 distinct statements. Never pad."""
    grouped: dict[str, dict] = {}
    for item in items or []:
        text = str(item or "").strip()
        if not text:
            continue
        code, title = _cluster_for(text)
        current = grouped.get(code)
        impact = _impact(code, text, deadline_fit)
        if current is None or impact > current["impact"] or len(text) > len(current["raw"]):
            grouped[code] = {
                "title": title,
                "raw": text,
                "impact": impact,
                "code": code,
            }

    ranked = sorted(grouped.values(), key=lambda row: (-row["impact"], row["code"]))
    selected = ranked[: max(0, min(limit, 5))]
    results: list[str] = []
    for row in selected:
        if row["code"] == "other":
            results.append(row["raw"])
            continue
        line = row["title"]
        detail = row["raw"].rstrip(".")
        if row["code"] == "deadline" and evidence:
            line = f"{line}. Evidence: {evidence}"
        elif detail.lower() not in line.lower():
            line = f"{line}. {detail}."
        results.append(re.sub(r"\s+", " ", line).strip())
    return results
