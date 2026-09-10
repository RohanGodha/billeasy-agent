"""Revenue-leakage risk scoring.

Distinct from module propensity, and the distinction matters:

* `propensity.py` answers *"which Billeasy module should this counter adopt?"*
* this module answers *"is money slipping off the digital rail at this counter right now?"*

They share the same feature math — the private builders in `propensity` are the single
source of truth for how a cash-share spike or a settlement mismatch is measured, so this
module imports them rather than reimplementing them and letting the two drift apart.

Unlike propensity, the combination here is a plain weighted sum, not a logistic. Weights
sum to 1.0 over features that are each in [0, 1], so the output reads directly as
"share of the maximum leakage evidence we could have seen" — 0.61 means 61%. That is
auditable in a way a squashed logit is not, which matters because this number is what
sends an Area Manager to a counter to ask a supervisor an uncomfortable question.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.domain import ScoreBreakdown
from app.scoring.propensity import (
    _RATIONALES,
    _cash_share_spike,
    _field_note_stress,
    _peak_hour_downtime,
    _pending_settlement_backlog,
    _receipt_issuance_gap,
    _refund_ratio,
    _settlement_mismatch_rate,
    _void_reissue_rate,
)

_WEIGHTS_PATH = Path(__file__).parent / "weights.yaml"
_WEIGHTS: dict[str, float] = (
    yaml.safe_load(_WEIGHTS_PATH.read_text(encoding="utf-8")).get("leakage") or {}
)

# Above this, the counter goes to the top of the action queue.
ESCALATION_THRESHOLD = 0.45


def severity_band(score: float) -> str:
    """Human label for a leakage score. Used in UI copy and the Area Manager summary."""
    if score >= 0.65:
        return "severe"
    if score >= ESCALATION_THRESHOLD:
        return "elevated"
    if score >= 0.25:
        return "watch"
    return "clear"


def compute_leakage_risk(
    counter: dict[str, Any],
    txns: list[dict[str, Any]],
    field_notes: list[dict[str, Any]],
) -> tuple[float, list[ScoreBreakdown]]:
    """Return (leakage risk in [0,1], explainable per-feature breakdown).

    Every contribution is `weight x feature`, and the weights live in `weights.yaml`
    so the thresholds can be re-tuned without a code change.
    """
    f: dict[str, float] = {
        "settlement_mismatch_rate": _settlement_mismatch_rate(txns),
        "cash_share_spike": _cash_share_spike(txns),
        "void_reissue_rate": _void_reissue_rate(txns),
        "receipt_issuance_gap": _receipt_issuance_gap(counter, txns),
        "peak_hour_downtime": _peak_hour_downtime(counter, txns, field_notes),
        "pending_settlement_backlog": _pending_settlement_backlog(counter),
        "field_note_stress_signal": _field_note_stress(field_notes),
        "refund_ratio": _refund_ratio(txns),
    }

    breakdowns: list[ScoreBreakdown] = []
    score = 0.0
    for feature, weight in _WEIGHTS.items():
        value = max(0.0, min(f.get(feature, 0.0), 1.0))
        contribution = weight * value
        score += contribution
        breakdowns.append(
            ScoreBreakdown(
                feature=feature,
                value=round(value, 3),
                contribution=round(contribution, 3),
                direction="negative" if contribution > 0.02 else "neutral",
                rationale=_RATIONALES.get(feature, ""),
            )
        )

    breakdowns.sort(key=lambda b: b.contribution, reverse=True)
    return round(max(0.0, min(score, 1.0)), 4), breakdowns
