"""Pydantic domain models. Tools and API responses use these directly."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Counter(BaseModel):
    """A live Billeasy counter: a retail POS outlet or a transit ticketing window."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    counter_type: Literal["retail", "ferry", "bus", "metro"]
    city: str
    tier: Literal["nano", "standard", "flagship", "anchor"]
    operator: str
    monthly_tpv: float
    onboarded_date: str
    kyc_status: str = "verified"
    phone: str
    email: str | None = None
    settlement_cycle: str = "T+1"

    # Enriched fields (joined from counter health / settlement tables)
    pending_settlement: float | None = None
    avg_daily_txns: float | None = None
    digital_share: float | None = None
    # Peak-window minutes the terminal was unreachable, from the device estate.
    # Must be declared here: the model is configured `extra="ignore"`, so a column the
    # SQL selects but the model does not declare is silently dropped on the way to the
    # scorers — which is exactly what happened to this one, leaving the downtime feature
    # permanently on its weaker inference fallback.
    device_offline_minutes: float | None = None
    # DPDP outreach consent: False means the merchant has opted out of WhatsApp / call
    # nudges, so no draft may be composed for them no matter the score. Must be declared
    # here too: with `extra="ignore"` an undecleared column is silently dropped, which
    # would leave the compliance gate permanently open.
    consent_ok: bool = True


class Transaction(BaseModel):
    """One row off the Billeasy rail.

    `category` is one of: ticket_sale, retail_bill, refund, void_reissue,
    settlement_payout, chargeback, topup, other.
    `channel` is one of: upi, card, cash, ncmc, wallet, netbanking.
    Collections (`ticket_sale`, `retail_bill`) and `settlement_payout` carry a
    positive amount; `refund` and `chargeback` carry a negative amount.
    """

    id: str
    counter_id: str
    ts: str
    amount: float
    category: str
    channel: str
    instrument: str | None = None


class Module(BaseModel):
    """A Billeasy SaaS module / SKU that can be live on a counter."""

    id: str
    name: str
    category: str
    take_rate: float | None = None
    min_monthly_tpv: float | None = None
    min_daily_txns: int | None = None
    max_daily_txns: int | None = None
    description: str | None = None
    eligibility: dict[str, Any] = Field(default_factory=dict)


class CounterFilters(BaseModel):
    """Used by `query_counters` tool. All optional, all AND-combined."""
    cities: list[str] | None = None
    tiers: list[str] | None = None
    counter_types: list[str] | None = None
    min_tpv: float | None = None
    max_tpv: float | None = None
    min_pending_settlement: float | None = None
    min_daily_txns: int | None = None
    max_daily_txns: int | None = None
    settlement_cycles: list[str] | None = None
    exclude_modules: list[str] | None = None
    limit: int = 200


class ScoreBreakdown(BaseModel):
    """Explainable contribution of a single feature to a score."""
    feature: str
    value: float
    contribution: float
    direction: Literal["positive", "negative", "neutral"] = "neutral"
    rationale: str


class Candidate(BaseModel):
    """A counter + scoring + recommendation, ready for the UI."""
    counter: Counter
    value_score: float = 0.0
    propensity_score: float = 0.0
    composite_score: float = 0.0
    leakage_risk: float = 0.0
    recommended_module_id: str | None = None
    recommended_module_name: str | None = None
    feature_contributions: list[ScoreBreakdown] = Field(default_factory=list)
    rationale: str = ""
    citations: list[str] = Field(default_factory=list)


class OutreachDraft(BaseModel):
    id: str
    session_id: str
    counter_id: str
    module_id: str
    channel: str = "whatsapp"
    message: str
    score: float | None = None
    compliance: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"
