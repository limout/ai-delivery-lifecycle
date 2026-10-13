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
    r"go[\s-]?live|complete(?:d)?|production|ready)(?:\s+(?:about|approximately|around))?\s*$",
    re.I,
)
_SOFT_DEADLINE_PREFIX = re.compile(r"(?:about|approximately|around)\s*$", re.I)
_DEADLINE_MARKERS = (
    "deadline", "within", "target", "timeline", "release", "go live",
    "go-live", "launch", "due", "complete", "production", "from now",
    "first production", "required by", "wants the", "ready for",
    "customer event", "in about", "in approximately",
)
_ESTIMATE_MARKERS = (
    "estimate", "estimated", "estimation", "of work",
    "we currently estimate", "our estimate", "team estimate",
)

COMMITMENT_CONTRACTUAL = "contractual"
COMMITMENT_INTERNAL_TARGET = "internal_target"
COMMITMENT_ASPIRATIONAL = "aspirational"
COMMITMENT_UNSPECIFIED = "unspecified"

_NOT_CONTRACTUAL = re.compile(
    r"\b(?:not|non)[-\s](?:a\s+|an\s+)?"
    r"(?:contractual|binding|mandatory|"
    r"approved(?:\s+\w+){0,2}\s+commitment|"
    r"(?:delivery\s+)?commitment)\b",
    re.I,
)
_INTERNAL_TARGET = re.compile(
    r"\b(?:internal\s+target|planning\s+target|planning\s+date|"
    r"planning\s+horizon|flexible\s+target|"
    r"this\s+is\s+(?:an?\s+)?(?:internal\s+|planning\s+|non[-\s]binding\s+)?target|"
    r"a\s+target,\s+not)\b",
    re.I,
)
_CONTRACTUAL_CLAIM = re.compile(
    r"\b(?:contractual\s+deadline|binding\s+deadline|mandatory\s+deadline|"
    r"hard\s+deadline|fixed\s+deadline|legally\s+binding|"
    r"liquidated\s+damages|penalt(?:y|ies)\b.{0,40}\bmiss|"
    r"date\s+is\s+contractual|deadline\s+is\s+contractual|"
    r"contractually\s+(?:required|binding|committed)|"
    r"is\s+a\s+contractual\s+(?:deadline|commitment|date))\b",
    re.I,
)
_ASPIRATIONAL = re.compile(
    r"\b(?:aspirational|stretch\s+goal|if\s+possible|"
    r"nice(?:-|\s+)to(?:-|\s+)have|hope\s+to|hoping\s+to)\b",
    re.I,
)
_STATED_DATE_PHRASE = {
    COMMITMENT_CONTRACTUAL: "contractual customer deadline",
    COMMITMENT_INTERNAL_TARGET: "stated internal target",
    COMMITMENT_ASPIRATIONAL: "stated aspirational date",
    COMMITMENT_UNSPECIFIED: "stated delivery date",
}
_COMMITMENT_FACT = {
    COMMITMENT_INTERNAL_TARGET: (
        "The stated date is an internal planning target, not a contractual "
        "or mandatory deadline."
    ),
    COMMITMENT_CONTRACTUAL: "The stated date is a contractual delivery deadline.",
    COMMITMENT_ASPIRATIONAL: (
        "The stated date is an aspirational planning preference, not a deadline."
    ),
}


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
    soft_prefix = bool(_SOFT_DEADLINE_PREFIX.search(immediate))
    from_now = bool(re.search(r"^\s*from now\b", after, re.I))

    if from_now or prefix_hit:
        return "deadline"
    if estimate_hit and not deadline_hit:
        return "estimate"
    if soft_prefix and not estimate_hit:
        return "deadline"
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


def _blob(texts: list[str] | None) -> str:
    return " ".join(str(item) for item in (texts or []) if str(item).strip())


def _has_positive_contractual_claim(text: str) -> bool:
    for match in _CONTRACTUAL_CLAIM.finditer(text or ""):
        before = text[max(0, match.start() - 24):match.start()].lower()
        if re.search(r"\b(?:not|non)[-\s](?:a\s+)?$", before):
            continue
        if before.rstrip().endswith("not a") or before.rstrip().endswith("not"):
            continue
        return True
    return False


def classify_date_commitment(texts: list[str] | None) -> str:
    """Classify a stated date as contractual, internal target, aspirational, or unspecified.

    Does not invent a contract when the source is silent. Explicit non-contractual
    or internal-target language wins over a nearby use of the word deadline and
    over a later model-written contractual claim in the same corpus.
    """
    blob = _blob(texts)
    if not blob.strip():
        return COMMITMENT_UNSPECIFIED
    not_contractual = bool(_NOT_CONTRACTUAL.search(blob))
    internal = bool(_INTERNAL_TARGET.search(blob))
    contractual = _has_positive_contractual_claim(blob)
    aspirational = bool(_ASPIRATIONAL.search(blob))
    if not_contractual or internal:
        return COMMITMENT_INTERNAL_TARGET
    if contractual:
        return COMMITMENT_CONTRACTUAL
    if aspirational:
        return COMMITMENT_ASPIRATIONAL
    return COMMITMENT_UNSPECIFIED


def sanitize_timeline_constraints(
    constraints: list | None,
    source_texts: list[str] | None,
) -> list[str]:
    """Keep duration facts; drop invented contractual claims that contradict the source."""
    kind = classify_date_commitment(source_texts)
    status = commitment_status_fact(kind)
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in constraints or []:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if (
            kind != COMMITMENT_CONTRACTUAL
            and _has_positive_contractual_claim(text)
            and not _NOT_CONTRACTUAL.search(text)
        ):
            continue
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    if status and status.lower() not in seen:
        cleaned.append(status)
    return cleaned


def stated_date_phrase(kind: str) -> str:
    return _STATED_DATE_PHRASE.get(kind, _STATED_DATE_PHRASE[COMMITMENT_UNSPECIFIED])


def commitment_status_fact(kind: str) -> str:
    return _COMMITMENT_FACT.get(kind, "")


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
