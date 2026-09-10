"""Numeric grounding validator for outreach drafts.

Every number that appears in a draft message must also appear in the source
context (counter profile, recommended module, txn aggregates). Any number that
fails grounding is either stripped or the draft is regenerated upstream.

This is the #1 failure mode in partner and merchant communications: never send a
counter supervisor or outlet owner a settlement, TPV or leakage figure the source
data does not support. We treat it as a first-class quality gate.
"""
from __future__ import annotations

import re
from typing import Any

_NUM_RE = re.compile(r"(?<![A-Za-z_])(?:₹|Rs\.?|INR)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)(?:\s*(?:%|lakhs?|crores?|L|Cr))?", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _extract_numbers(text: str) -> list[str]:
    nums: list[str] = []
    for m in _NUM_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        if not raw:
            continue
        # Filter out four-digit years like 2024 (handled separately)
        if _YEAR_RE.fullmatch(m.group(0).strip()):
            continue
        nums.append(raw)
    return nums


def _flatten(value: Any, bag: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, (int, float)):
        s = f"{value:.2f}".rstrip("0").rstrip(".")
        bag.append(s)
        bag.append(str(int(value))) if value == int(value) else None  # also raw int form
        # Common abbreviations
        if value >= 100000:
            bag.append(f"{value / 100000:.1f}".rstrip("0").rstrip("."))
            bag.append(f"{value / 100000:.0f}")
        if value >= 10000000:
            bag.append(f"{value / 10000000:.1f}".rstrip("0").rstrip("."))
            bag.append(f"{value / 10000000:.0f}")
        return
    if isinstance(value, str):
        for m in _NUM_RE.finditer(value):
            bag.append(m.group(1).replace(",", ""))
        return
    if isinstance(value, dict):
        for v in value.values():
            _flatten(v, bag)
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            _flatten(v, bag)
        return


def compliance_check(draft: str, source_context: dict[str, Any]) -> dict[str, Any]:
    """Return a compliance report and a redacted draft if needed."""
    in_draft = _extract_numbers(draft)
    bag: list[str] = []
    _flatten(source_context, bag)
    allowed = set(bag)

    ungrounded: list[str] = []
    for n in in_draft:
        if n in allowed:
            continue
        # tolerate small rounding (e.g. ₹18.4 lakh vs 18.4)
        try:
            f = float(n)
            ok = any(abs(f - float(a)) <= max(0.05 * abs(f), 1.0) for a in allowed if _is_number(a))
            if not ok:
                ungrounded.append(n)
        except ValueError:
            ungrounded.append(n)

    redacted = draft
    for n in ungrounded:
        redacted = re.sub(_redaction_pattern(n), "—", redacted)

    return {
        "ok": len(ungrounded) == 0,
        "numbers_in_draft": in_draft,
        "ungrounded": ungrounded,
        "redacted_draft": redacted if ungrounded else draft,
    }


def _redaction_pattern(n: str) -> str:
    """Match an ungrounded number back in the draft, however it was punctuated.

    Numbers are normalised without separators when they are extracted (``9,87,654`` ->
    ``987654``), so redacting the normalised literal silently failed against the
    original text — the draft was correctly reported non-compliant while still
    containing the invented figure. Since a model writes rupee amounts with Indian
    digit grouping, that covered essentially every hallucinated amount.

    Allowing an optional separator between digits makes the redaction match the
    ``9,87,654``, ``987,654`` and ``987654`` forms alike.
    """
    if "." in n:
        int_part, frac = n.split(".", 1)
        body = ",?".join(re.escape(c) for c in int_part) + re.escape(".") + re.escape(frac)
    else:
        body = ",?".join(re.escape(c) for c in n)
    # Digit lookarounds stop a short number redacting part of a longer one.
    return rf"(?<![A-Za-z_0-9]){body}(?![A-Za-z_0-9])"


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False
