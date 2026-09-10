"""Per-module propensity scoring for Billeasy counters.

Logistic combination of module-specific features. All features in [-1, 1] roughly.
Returns (score in [0,1], list of ScoreBreakdown) so the agent has an audit trail
the Area Partner Manager can read back to a depot supervisor or outlet owner.

Calibration bands
-----------------
Some leakage features are *rate* signals whose raw value is tiny even when the
counter is badly broken (a 12% void-reissue rate is a fraud investigation, not a
0.12 nudge). Those are normalised against an operational band — below the lower
edge is routine noise, at the upper edge the counter is red-lined:

  void_reissue_rate         2%  ->  15%
  settlement_mismatch_rate  2%  ->  20%
  cash_share_spike        +5pp  -> +35pp   (recent share vs the counter's own baseline)
  pending_settlement_backlog 5% ->  40%    (pending payout as a share of monthly TPV)
  refund_ratio              1%  ->  15%

The raw, unnormalised aggregates are exposed separately by
`get_counter_transactions`; these are the scoring views of them.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from app.domain import ScoreBreakdown

_WEIGHTS_PATH = Path(__file__).parent / "weights.yaml"
_WEIGHTS: dict[str, Any] = yaml.safe_load(_WEIGHTS_PATH.read_text(encoding="utf-8"))

# Transaction vocabulary (see domain.Transaction).
_SALE_CATEGORIES = {"ticket_sale", "retail_bill"}
_DIGITAL_CHANNELS = {"upi", "card", "ncmc", "wallet", "netbanking"}
_CASH_CHANNEL = "cash"

# Peak commuting / retail rush windows used for downtime attribution. Kept as two
# named windows rather than one flat set: a depot counter that sells all morning and
# then goes dark at 17:00 is the case that matters, and a whole-day test cannot see it.
_PEAK_WINDOWS: dict[str, set[int]] = {
    "morning": {8, 9, 10, 11},
    "evening": {17, 18, 19, 20},
}
_PEAK_HOURS = _PEAK_WINDOWS["morning"] | _PEAK_WINDOWS["evening"]

# Billeasy module catalogue: id -> SaaS category (mirrors the modules table).
_MODULE_CATEGORY: dict[str, str] = {
    "MOD-BILLING": "billing",
    "MOD-ETICKET": "ticketing",
    "MOD-QR": "payments",
    "MOD-RECON": "reconciliation",
    "MOD-OFFLINE": "payments",
    "MOD-LOYALTY": "loyalty",
    "MOD-WA-RECEIPT": "engagement",
    "MOD-ANALYTICS": "analytics",
}

# Optimal daily-txn band per module: (floor from the module catalogue, practical ceiling).
_MODULE_TXN_BANDS: dict[str, tuple[int, int]] = {
    "MOD-BILLING": (20, 400),
    "MOD-ETICKET": (150, 2000),
    "MOD-QR": (10, 300),
    "MOD-RECON": (100, 1200),
    "MOD-OFFLINE": (80, 900),
    "MOD-LOYALTY": (40, 600),
    "MOD-WA-RECEIPT": (15, 400),
    "MOD-ANALYTICS": (25, 800),
}


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _norm(x: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return max(min((x - lo) / (hi - lo), 1.0), 0.0)


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(min(x, hi), lo)


def _amount(t: dict[str, Any]) -> float:
    try:
        return float(t.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00").replace("+00:00", ""))
    except Exception:  # noqa: BLE001
        return None


def _sales(txns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in txns if t.get("category") in _SALE_CATEGORIES]


def _collections(txns: list[dict[str, Any]]) -> float:
    """Gross ₹ captured at the counter (ticket sales + retail bills)."""
    return sum(abs(_amount(t)) for t in _sales(txns))


# ---------------------------------------------------------------------------
# Windowing: a counter is always compared against its OWN earlier baseline,
# never against the network — that is what makes a "spike" a spike.
# ---------------------------------------------------------------------------

def _split_baseline_recent(
    txns: list[dict[str, Any]], recent_days: int = 30
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (baseline, recent) transaction windows for the same counter."""
    dated = [(d, t) for t in txns if (d := _parse_ts(t.get("ts", ""))) is not None]
    if len(dated) >= 6:
        dated.sort(key=lambda p: p[0])
        cutoff = dated[-1][0] - timedelta(days=recent_days)
        recent = [t for d, t in dated if d > cutoff]
        baseline = [t for d, t in dated if d <= cutoff]
        if len(recent) >= 3 and len(baseline) >= 3:
            return baseline, recent
        ordered = [t for _, t in dated]
    else:
        ordered = sorted(txns, key=lambda t: str(t.get("ts", "")))
    if len(ordered) < 4:
        return [], ordered
    split = max(int(len(ordered) * 0.6), 1)
    return ordered[:split], ordered[split:]


def _cash_share(txns: list[dict[str, Any]]) -> float:
    sales = _sales(txns)
    total = sum(abs(_amount(t)) for t in sales)
    if total <= 0:
        return 0.0
    cash = sum(abs(_amount(t)) for t in sales if t.get("channel") == _CASH_CHANNEL)
    return cash / total


def _digital_share_of(txns: list[dict[str, Any]]) -> float:
    sales = _sales(txns)
    total = sum(abs(_amount(t)) for t in sales)
    if total <= 0:
        return 0.0
    digital = sum(abs(_amount(t)) for t in sales if t.get("channel") in _DIGITAL_CHANNELS)
    return digital / total


# ---------------------------------------------------------------------------
# Feature builders. Each returns float in roughly [-1, 1] (most only [0, 1]).
# ---------------------------------------------------------------------------

def _cash_share_spike(txns: list[dict[str, Any]]) -> float:
    """Recent cash share of collections minus this counter's own baseline."""
    baseline, recent = _split_baseline_recent(txns)
    if not baseline or not recent:
        return 0.0
    delta = _cash_share(recent) - _cash_share(baseline)
    return _norm(delta, 0.05, 0.35)


def _digital_share_trend(txns: list[dict[str, Any]]) -> float:
    """+1 the digital rail is winning share, -1 fares are drifting back to cash."""
    baseline, recent = _split_baseline_recent(txns)
    if not baseline or not recent:
        return 0.0
    return _clamp((_digital_share_of(recent) - _digital_share_of(baseline)) * 2.0)


def _monthly_collections(txns: list[dict[str, Any]]) -> list[float]:
    buckets: dict[str, float] = {}
    for t in _sales(txns):
        d = _parse_ts(t.get("ts", ""))
        key = d.strftime("%Y-%m") if d else str(t.get("ts", ""))[:7]
        if not key:
            continue
        buckets[key] = buckets.get(key, 0.0) + abs(_amount(t))
    return [buckets[k] for k in sorted(buckets)]


def _tpv_growth_trend(txns: list[dict[str, Any]]) -> float:
    """Month-over-month TPV growth: +1 growing, -1 collapsing, 0 flat."""
    months = _monthly_collections(txns)
    if len(months) < 2:
        return 0.0
    if len(months) >= 4:
        recent = sum(months[-2:]) / 2.0
        older = sum(months[:-2]) / max(len(months) - 2, 1)
    else:
        recent = months[-1]
        older = sum(months[:-1]) / max(len(months) - 1, 1)
    if older <= 0:
        return 0.0
    return _clamp(((recent - older) / older) * 2.0)


def _txn_velocity(counter: dict[str, Any], txns: list[dict[str, Any]]) -> float:
    """Normalised average daily transactions (0 -> 400 txns/day)."""
    daily = counter.get("avg_daily_txns")
    if daily is None:
        dated = sorted(d for t in txns if (d := _parse_ts(t.get("ts", ""))) is not None)
        span = max((dated[-1] - dated[0]).days, 1) if len(dated) >= 2 else 1
        daily = len(_sales(txns)) / span
    try:
        return _norm(float(daily), 0, 400)
    except (TypeError, ValueError):
        return 0.0


def _void_reissue_rate(txns: list[dict[str, Any]]) -> float:
    """Tickets issued, voided, then reissued — the classic pocket-the-cash pattern."""
    sales = len(_sales(txns))
    if sales == 0:
        return 0.0
    voids = sum(1 for t in txns if t.get("category") == "void_reissue")
    return _norm(voids / sales, 0.02, 0.15)


def _settlement_mismatch_rate(txns: list[dict[str, Any]]) -> float:
    """(collected - settled) / collected, normalised against the 2%-20% band."""
    collected = _collections(txns)
    settled = sum(abs(_amount(t)) for t in txns if t.get("category") == "settlement_payout")
    if collected <= 0 or settled <= 0:
        # No payout evidence at all is missing data, not a mismatch.
        return 0.0
    gap = (collected - settled) / collected
    if gap <= 0:
        return 0.0
    return _norm(gap, 0.02, 0.20)


def _pending_settlement_backlog(counter: dict[str, Any]) -> float:
    """₹ awaiting payout as a share of monthly TPV — a T+1 rail should sit near 3%."""
    try:
        pending = float(counter.get("pending_settlement") or 0)
        tpv = float(counter.get("monthly_tpv") or 0)
    except (TypeError, ValueError):
        return 0.0
    if tpv <= 0 or pending <= 0:
        return 0.0
    return _norm(pending / tpv, 0.05, 0.40)


def _receipt_issuance_gap(counter: dict[str, Any], txns: list[dict[str, Any]]) -> float:
    """Share of collections with no GST bill / e-ticket reference on the rail."""
    explicit = counter.get("receipt_issuance_gap")
    if explicit is not None:
        try:
            return _norm(float(explicit), 0.0, 1.0)
        except (TypeError, ValueError):
            pass
    sales = _sales(txns)
    if not sales:
        return 0.0
    unbilled = sum(1 for t in sales if not str(t.get("instrument") or "").strip())
    return unbilled / len(sales)


def _peak_hour_downtime(
    counter: dict[str, Any], txns: list[dict[str, Any]], field_notes: list[dict[str, Any]]
) -> float:
    """Device dark during the rush — every minute offline is an unrecorded fare."""
    minutes = counter.get("device_offline_minutes")
    if minutes is not None:
        try:
            return _norm(float(minutes), 0, 240)  # a full 4-hour peak = 1.0
        except (TypeError, ValueError):
            pass

    # Fallback: infer from holes in the transaction clock, per (day, peak window).
    sales_by_day_window: dict[tuple[str, str], int] = {}
    active_days: set[str] = set()
    for t in _sales(txns):
        d = _parse_ts(t.get("ts", ""))
        if d is None:
            continue
        day = d.strftime("%Y-%m-%d")
        active_days.add(day)
        for window, hours in _PEAK_WINDOWS.items():
            if d.hour in hours:
                key = (day, window)
                sales_by_day_window[key] = sales_by_day_window.get(key, 0) + 1

    signal = 0.0
    if len(active_days) >= 4:
        dark_slots = 0
        judged_slots = 0
        for window in _PEAK_WINDOWS:
            served = sum(1 for day in active_days if sales_by_day_window.get((day, window), 0) > 0)
            # Only judge a window this counter actually trades in. A morning-only jetty
            # is not "down" every evening — it is closed, which is not a leak.
            if served < len(active_days) * 0.5:
                continue
            judged_slots += len(active_days)
            dark_slots += len(active_days) - served
        if judged_slots:
            signal = dark_slots / judged_slots

    text = " ".join(str(n.get("summary") or "").lower() for n in field_notes)
    if any(k in text for k in ("device down", "offline", "machine hang", "printer", "battery", "network")):
        signal = max(signal, 0.35)
    return _norm(signal, 0.0, 1.0)


def _refund_ratio(txns: list[dict[str, Any]]) -> float:
    collected = _collections(txns)
    if collected <= 0:
        return 0.0
    refunds = sum(abs(_amount(t)) for t in txns if t.get("category") == "refund")
    return _norm(refunds / collected, 0.01, 0.15)


def _ncmc_share(txns: list[dict[str, Any]]) -> float:
    """Share of transit ticket sales tapped on an NCMC card."""
    transit = [t for t in txns if t.get("category") == "ticket_sale"]
    if not transit:
        return 0.0
    ncmc = sum(1 for t in transit if t.get("channel") == "ncmc")
    return ncmc / len(transit)


def _has_module(
    holdings: list[dict[str, Any]], category: str | None = None, module_id: str | None = None
) -> bool:
    for h in holdings:
        held_id = h.get("module_id") or h.get("id")
        if module_id and held_id == module_id:
            return True
        if category and h.get("category") == category:
            return True
    return False


def _field_note_stress(field_notes: list[dict[str, Any]]) -> float:
    keywords = [
        "device down", "not settling", "payout delayed", "printer", "network",
        "complaint", "escalation", "cash only", "machine hang", "dispute",
        "chargeback", "queue", "offline", "reconciliation", "mismatch", "unpaid",
    ]
    for note in field_notes:
        s = str(note.get("summary") or "").lower()
        if any(k in s for k in keywords):
            return 1.0
    return 0.0


def _daily_txn_band(counter: dict[str, Any], module_id: str) -> float:
    """Triangular fit inside the module's optimal daily-transaction band."""
    band = _MODULE_TXN_BANDS.get(module_id)
    if band is None:
        return 0.0
    lo, hi = band
    try:
        daily = float(counter.get("avg_daily_txns") or 0)
    except (TypeError, ValueError):
        return 0.0
    if lo <= daily <= hi:
        center = (lo + hi) / 2
        width = (hi - lo) / 2 or 1
        return 1.0 - abs(daily - center) / width
    return 0.0


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def predict_propensity(
    counter: dict[str, Any],
    txns: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    field_notes: list[dict[str, Any]],
    module_id: str,
) -> tuple[float, list[ScoreBreakdown]]:
    """Return (propensity in [0,1], explainable breakdown)."""
    weights = _WEIGHTS["propensity"].get(module_id)
    if weights is None:
        return 0.0, []

    try:
        tpv = float(counter.get("monthly_tpv") or 0)
    except (TypeError, ValueError):
        tpv = 0.0
    counter_type = str(counter.get("counter_type") or "")
    module_category = _MODULE_CATEGORY.get(module_id)

    f: dict[str, float] = {}

    # --- revenue leakage -----------------------------------------------------
    f["digital_share_trend"] = _digital_share_trend(txns)
    f["cash_share_spike"] = _cash_share_spike(txns)
    f["tpv_growth_trend"] = _tpv_growth_trend(txns)
    f["tpv_dropping"] = max(-f["tpv_growth_trend"], 0.0)
    f["txn_velocity"] = _txn_velocity(counter, txns)
    f["void_reissue_rate"] = _void_reissue_rate(txns)

    # --- settlement & compliance --------------------------------------------
    f["settlement_mismatch_rate"] = _settlement_mismatch_rate(txns)
    f["pending_settlement_backlog"] = _pending_settlement_backlog(counter)
    f["receipt_issuance_gap"] = _receipt_issuance_gap(counter, txns)
    f["gst_threshold_crossed"] = 1.0 if tpv >= 500000 else 0.0
    f["peak_hour_downtime"] = _peak_hour_downtime(counter, txns, field_notes)
    f["refund_ratio"] = _refund_ratio(txns)
    f["ncmc_share"] = _ncmc_share(txns)

    # --- white space on the counter -----------------------------------------
    f["no_existing_module_bonus"] = (
        0.0 if _has_module(holdings, category=module_category, module_id=module_id) else 1.0
    )
    f["no_recon_module"] = 0.0 if _has_module(holdings, module_id="MOD-RECON") else 1.0
    f["no_loyalty_module"] = 0.0 if _has_module(holdings, module_id="MOD-LOYALTY") else 1.0
    f["no_eticket_module"] = 0.0 if _has_module(holdings, module_id="MOD-ETICKET") else 1.0

    # --- counter profile -----------------------------------------------------
    f["tenure_long"] = _norm(_months_between_safe(counter.get("onboarded_date", "")), 3, 60)
    f["daily_txn_band_fit"] = _daily_txn_band(counter, module_id)
    f["tpv_above_2l"] = 1.0 if tpv >= 200000 else 0.0
    f["tpv_above_5l"] = 1.0 if tpv >= 500000 else 0.0
    f["tpv_above_10l"] = 1.0 if tpv >= 1000000 else 0.0
    f["field_note_stress_signal"] = _field_note_stress(field_notes)
    f["transit_counter_fit"] = 1.0 if counter_type in {"ferry", "bus", "metro"} else 0.0
    f["retail_counter_fit"] = 1.0 if counter_type == "retail" else 0.0

    breakdowns: list[ScoreBreakdown] = []
    raw = 0.0
    for feat_name, weight in weights.items():
        value = f.get(feat_name, 0.0)
        contribution = weight * value
        raw += contribution
        direction = "positive" if contribution > 0.02 else ("negative" if contribution < -0.02 else "neutral")
        breakdowns.append(
            ScoreBreakdown(
                feature=feat_name,
                value=round(value, 3),
                contribution=round(contribution, 3),
                direction=direction,
                rationale=_RATIONALES.get(feat_name, ""),
            )
        )
    score = _sigmoid(raw * 2.5)  # scale to widen the curve
    return round(score, 4), sorted(breakdowns, key=lambda b: abs(b.contribution), reverse=True)


def _months_between_safe(iso: str) -> int:
    from datetime import datetime as _dt

    try:
        return max(int((_dt.utcnow() - _dt.fromisoformat(iso)).days / 30), 0)
    except Exception:  # noqa: BLE001
        return 0


_RATIONALES: dict[str, str] = {
    "digital_share_trend": "Direction of the digital rail's share of collections at this counter.",
    "cash_share_spike": "Cash share jumped versus this counter's baseline — fares may be bypassing the digital rail.",
    "tpv_growth_trend": "Month-on-month movement in ₹ collected at this counter.",
    "tpv_dropping": "Collections are falling month on month — footfall, device or diversion issue.",
    "txn_velocity": "Daily transaction volume — how hard this counter is actually working.",
    "void_reissue_rate": "Tickets issued, voided and reissued — the classic cash-pocketing pattern.",
    "settlement_mismatch_rate": "₹ captured at the counter does not reconcile with ₹ settled out.",
    "pending_settlement_backlog": "Payout backlog is aging against monthly TPV — the partner is waiting for money.",
    "receipt_issuance_gap": "Collections taken without a GST bill or e-ticket on the rail.",
    "gst_threshold_crossed": "Monthly TPV is past the ₹5L e-invoice mandate band — compliant billing is now non-optional.",
    "peak_hour_downtime": "Terminal was dark during the rush — every offline minute is an unrecorded fare.",
    "refund_ratio": "Refunds against collections — disputes or mis-punched tickets at this window.",
    "ncmc_share": "Share of transit sales already tapping NCMC cards.",
    "no_existing_module_bonus": "This Billeasy module category is not live on the counter yet — open white space.",
    "no_recon_module": "Settlement & Fare Reconciliation is not live on this counter.",
    "no_loyalty_module": "Loyalty & Rewards is not live on this counter.",
    "no_eticket_module": "Transit e-Ticketing (QR + NCMC) is not live on this counter.",
    "tenure_long": "Months live on the Billeasy rail — a settled partner adopts faster.",
    "daily_txn_band_fit": "Daily transaction volume sits inside this module's sweet spot.",
    "tpv_above_2l": "Monthly TPV clears the ₹2L entry band for paid modules.",
    "tpv_above_5l": "Monthly TPV clears the ₹5L mid band.",
    "tpv_above_10l": "Monthly TPV clears the ₹10L anchor-counter band.",
    "field_note_stress_signal": "Field-visit notes flag device, payout or complaint trouble at this counter.",
    "transit_counter_fit": "Transit counter (ferry jetty, bus depot or metro station) — fits the fare-revenue modules.",
    "retail_counter_fit": "Retail outlet — fits the billing, loyalty and engagement modules.",
}
