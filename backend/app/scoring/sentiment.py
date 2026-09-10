"""Sentiment + attrition-risk analysis over a counter's field-visit notes.

Adapted from the VFS RAG bot's sentiment/escalation pattern, but fitted to a
Billeasy Area Partner Manager context: instead of routing an angry user to a live
agent, we score each *candidate counter's* recent field notes and support tickets
and flag negative-sentiment / at-risk counters for priority human attention (a
site visit, a payout escalation, a device swap).

Deterministic + rule-based so it runs offline and fast (no LLM needed). When a
real LLM is configured the synthesizer can optionally refine it, but the rules
already capture the high-signal cues present in field-ops notes.
"""
from __future__ import annotations

from typing import Any, Literal

Sentiment = Literal["positive", "neutral", "negative"]

_NEGATIVE = {
    "device down", "not settling", "payout delayed", "printer", "network",
    "complaint", "complain", "escalation", "escalate", "cash only", "machine hang",
    "dispute", "chargeback", "queue", "offline", "battery", "reconciliation",
    "mismatch", "unpaid", "delay", "delayed", "pending payout", "failed", "failure",
    "not working", "downtime", "unhappy", "frustrated", "issue", "problem",
}
_POSITIVE = {
    "happy", "increase", "expand", "more counters", "training done",
    "settled on time", "smooth", "adoption", "satisfied", "keen", "appreciate",
    "thanks", "thank you", "on time", "helpful",
}
_CHURN = {
    "switch", "competitor", "terminate", "remove device", "stop using",
    "deactivate", "return the device", "cancel", "moving to", "shut the counter",
}


def analyze_sentiment(field_notes: list[dict[str, Any]]) -> dict[str, Any]:
    """Return {sentiment, score, escalate, churn_risk, signals[]}.

    This reads what people *wrote* about a counter — field-visit notes and support
    tickets. It deliberately does NOT produce the leakage score: revenue leakage is
    computed from transaction evidence in `scoring/leakage.py`, because a counter can
    leak quietly with a spotless support history. Keeping the two separate stops a
    complaint from being mistaken for evidence, and silence from being mistaken for
    health.
    """
    if not field_notes:
        return {
            "sentiment": "neutral",
            "score": 0.0,
            "escalate": False,
            "churn_risk": False,
            "signals": [],
        }

    text = " ".join((n.get("summary") or "").lower() for n in field_notes)
    signals: list[str] = []

    neg = sum(1 for kw in _NEGATIVE if kw in text)
    pos = sum(1 for kw in _POSITIVE if kw in text)
    churn = [kw for kw in _CHURN if kw in text]

    for kw in _NEGATIVE:
        if kw in text:
            signals.append(kw)

    # Net score in [-1, 1]
    total = neg + pos
    score = 0.0 if total == 0 else round((pos - neg) / total, 3)

    sentiment: Sentiment = "neutral"
    if score <= -0.34 or neg >= 2:
        sentiment = "negative"
    elif score >= 0.34 and neg == 0:
        sentiment = "positive"

    churn_risk = len(churn) > 0 or neg >= 3
    escalate = sentiment == "negative" or churn_risk

    return {
        "sentiment": sentiment,
        "score": score,
        "escalate": escalate,
        "churn_risk": churn_risk,
        "signals": signals[:5],
    }
