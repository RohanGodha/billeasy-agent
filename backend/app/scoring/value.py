"""Counter network-value scoring — transparent and explainable.

For each candidate counter we compute:
  value_score = sigmoid(weighted sum of z-scored features)

Features are z-scored against the counter population currently in play, so the
score always answers "how valuable is this counter *relative to this area's
network*". We return the score AND the feature contributions so the agent can
quote them back to the Area Partner Manager.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from app.domain import ScoreBreakdown

_WEIGHTS_PATH = Path(__file__).parent / "weights.yaml"
_WEIGHTS: dict[str, Any] = yaml.safe_load(_WEIGHTS_PATH.read_text(encoding="utf-8"))


def _months_between(iso_date: str) -> int:
    try:
        d = datetime.fromisoformat(iso_date)
    except Exception:  # noqa: BLE001
        return 0
    delta = datetime.utcnow() - d
    return max(int(delta.days / 30), 0)


def _zscore(value: float, population: list[float]) -> float:
    if not population:
        return 0.0
    arr = np.array(population, dtype=float)
    mu = float(arr.mean())
    sigma = float(arr.std()) or 1.0
    return (value - mu) / sigma


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def compute_value(
    counter: dict[str, Any],
    population: list[dict[str, Any]],
    txn_count_6m: int = 0,
) -> tuple[float, list[ScoreBreakdown]]:
    """Return (value_score in [0,1], list of feature contributions)."""
    w = _WEIGHTS["value"]

    tpvs = [float(c.get("monthly_tpv") or 0) for c in population]
    digital_shares = [float(c.get("digital_share") or 0) for c in population]
    tenures = [float(_months_between(c.get("onboarded_date", ""))) for c in population]
    velocities = [float(c.get("_txn_velocity") or 0) for c in population]

    tpv = float(counter.get("monthly_tpv") or 0)
    digital_share = float(counter.get("digital_share") or 0)
    tenure = float(_months_between(counter.get("onboarded_date", "")))
    velocity = float(txn_count_6m)

    tz_tpv = _zscore(tpv, tpvs)
    dz = _zscore(digital_share, digital_shares)
    tz = _zscore(tenure, tenures)
    vz = _zscore(velocity, velocities)

    contribs = [
        ("tpv_z", tz_tpv, w["tpv_z"], "Monthly TPV (₹) vs the rest of the counter network."),
        ("digital_share_z", dz, w["digital_share_z"], "Share of TPV riding the digital rail vs the network."),
        ("tenure_z", tz, w["tenure_z"], "Months live on Billeasy vs the network."),
        ("txn_velocity_z", vz, w["txn_velocity_z"], "Transaction velocity (count, 6m) vs the network."),
    ]

    raw = sum(weight * z for (_, z, weight, _) in contribs)
    score = _sigmoid(raw)

    breakdowns = [
        ScoreBreakdown(
            feature=name,
            value=round(z, 3),
            contribution=round(z * weight, 3),
            direction=("positive" if z * weight > 0.02 else ("negative" if z * weight < -0.02 else "neutral")),
            rationale=rationale,
        )
        for (name, z, weight, rationale) in contribs
    ]
    return round(score, 4), breakdowns
