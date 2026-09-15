"""Extract requested deadlines vs customer estimates from free text.

Deadline fit must use the requested date, never the customer's own estimate.
Duration units may be days, weeks, or months. Bare durations without a
deadline or estimate cue are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WEEKS_PER_MONTH = 4.345

NUMBER_WORDS = {
    "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
    "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0,
    "nine": 9.0, "ten": 10.0, "eleven": 11.0, "twelve": 12.0,
}

_NUMBER = r"(?:\d+(?:[.,]\d+)?|" + "|".join(NUMBER_WORDS) + r")"
_UNIT = r"(days?|weeks?|months?)"
_RANGE = re.compile(
    rf"({_NUMBER})\s*(?:-|–|—|to)\s*({_NUMBER})\s*{_UNIT}",
    re.I,
)
_SINGLE = re.compile(rf"({_NUMBER})\s*{_UNIT}", re.I)

_DEADLINE_PREFIX = re.compile(
    r"(?:within|in|by|before|deadline|due|target|timeline|release|launch|"
    r"go[\s-]?live|complete(?:d)?|production|from now)\s*$",
    re.I,
)
_DEADLINE_MARKERS = (
    "deadline", "within", "target", "timeline", "release", "go live",
    "go-live", "launch", "due", "complete", "production", "from now",
    "first production", "required by", "wants the",
)
_ESTIMATE_MARKERS = (
    "estimate", "estimated", "estimation", "of work",
    "we currently estimate", "our estimate", "team estimate",
)


@dataclass(frozen=True)
class TimelineSpan:
    kind: str  # "deadline" | "estimate"
    weeks: float
    display: str
    raw: str


def _parse_number(token: str) -> float:
    token = token.strip().lower().replace(",", ".")
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    return float(token)


def _to_weeks(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("day"):
        return value / 7.0
    if unit.startswith("month"):
        return value * WEEKS_PER_MONTH
    return value


def _format_display(low: float, high: float, unit: str) -> str:
    unit = unit.lower()
    if unit.startswith("day"):
        label = "day" if high == 1 else "days"
    elif unit.startswith("month"):
        label = "month" if high == 1 else "months"
    else:
        label = "week" if high == 1 else "weeks"

    def fmt(value: float) -> str:
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:g}"

    if abs(low - high) < 1e-9:
        return f"{fmt(high)} {label}"
    return f"{fmt(low)}-{fmt(high)} {label}"


def _classify(text: str, start: int, end: int) -> str | None:
    before = text[max(0, start - 80):start]
    after = text[end:min(len(text), end + 80)]
    window = f"{before} {after}".lower()
    immediate = re.sub(r"[\s:.\-]+$", "", re.sub(r"\s+", " ", before[-40:]).strip())

    estimate_hit = any(marker in window for marker in _ESTIMATE_MARKERS)
    deadline_hit = any(marker in window for marker in _DEADLINE_MARKERS)
    prefix_hit = bool(_DEADLINE_PREFIX.search(immediate))
    from_now = bool(re.search(r"^\s*from now\b", after, re.I))

    if prefix_hit or from_now:
        return "deadline"
    if estimate_hit and not deadline_hit:
        return "estimate"
    if deadline_hit and not estimate_hit:
        return "deadline"
    if estimate_hit:
        return "estimate"
    if deadline_hit:
        return "deadline"
    return None


def extract_timeline_spans(text: str) -> list[TimelineSpan]:
    """Return classified duration spans from a single text blob."""
    source = str(text or "").replace("–", "-").replace("—", "-")
    spans: list[TimelineSpan] = []
    occupied: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= a or start >= b) for a, b in occupied)

    for match in _RANGE.finditer(source):
        start, end = match.span()
        if overlaps(start, end):
            continue
        kind = _classify(source, start, end)
        if not kind:
            continue
        low = _parse_number(match.group(1))
        high = _parse_number(match.group(2))
        unit = match.group(3)
        occupied.append((start, end))
        spans.append(
            TimelineSpan(
                kind=kind,
                weeks=_to_weeks(max(low, high), unit),
                display=_format_display(min(low, high), max(low, high), unit),
                raw=match.group(0),
            )
        )

    for match in _SINGLE.finditer(source):
        start, end = match.span()
        if overlaps(start, end):
            continue
        kind = _classify(source, start, end)
        if not kind:
            continue
        value = _parse_number(match.group(1))
        unit = match.group(2)
        occupied.append((start, end))
        spans.append(
            TimelineSpan(
                kind=kind,
                weeks=_to_weeks(value, unit),
                display=_format_display(value, value, unit),
                raw=match.group(0),
            )
        )

    return spans


def collect_spans(texts: list[str] | None) -> list[TimelineSpan]:
    spans: list[TimelineSpan] = []
    for text in texts or []:
        spans.extend(extract_timeline_spans(str(text)))
    return spans


def parse_requested_deadline(texts: list[str] | None) -> TimelineSpan | None:
    deadlines = [span for span in collect_spans(texts) if span.kind == "deadline"]
    if not deadlines:
        return None
    return min(deadlines, key=lambda span: span.weeks)


def parse_customer_estimate(texts: list[str] | None) -> TimelineSpan | None:
    estimates = [span for span in collect_spans(texts) if span.kind == "estimate"]
    if not estimates:
        return None
    return estimates[0]


def deadline_source_texts(
    user_request: str = "",
    discovery: dict | None = None,
    clarification_history: list | None = None,
    clarification_answers: list | None = None,
) -> list[str]:
    """Customer-authored sources only. Do not scan model-written business_goal."""
    texts = [str(user_request or "")]
    discovery = discovery or {}
    for item in discovery.get("constraints") or []:
        texts.append(str(item))
    for item in clarification_history or []:
        if isinstance(item, dict):
            texts.append(str(item.get("answer") or ""))
        else:
            texts.append(str(item))
    for item in clarification_answers or []:
        texts.append(str(item))
    return texts
