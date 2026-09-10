"""Synthesizer node — merges tool outputs into a ranked CandidateRecord list and a text summary."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.knowledge import MODULES
from app.agent.state import AgentState, CandidateRecord, TraceEvent
from app.infrastructure.llm import LLMMessage, get_llm_router
from app.scoring.leakage import ESCALATION_THRESHOLD, compute_leakage_risk, severity_band

_SYS = (Path(__file__).parent.parent / "prompts" / "synthesizer_system.md").read_text(encoding="utf-8")

# Module id -> display name, so a counter that fell out of the eligibility pass
# still renders "Settlement & Fare Reconciliation" rather than a raw SKU code.
_MODULE_NAME: dict[str, str] = {m["id"]: m["name"] for m in MODULES}

# Per-transaction commission Billeasy earns on each module (%), used only to size
# the opportunity for prioritisation. Mirrors the module catalogue.
_TAKE_RATE: dict[str, float] = {
    "MOD-BILLING": 0.4,
    "MOD-ETICKET": 1.2,
    "MOD-QR": 0.6,
    "MOD-RECON": 0.5,
    "MOD-OFFLINE": 0.7,
    "MOD-LOYALTY": 0.8,
    "MOD-WA-RECEIPT": 0.3,
    "MOD-ANALYTICS": 0.5,
}

# Remediation modules fix a live leak. They target the counters that are bleeding,
# regardless of how big those counters are → propensity dominates the ranking.
_REMEDIATION = {"MOD-RECON", "MOD-OFFLINE"}


def _by_step(state: AgentState, tool_name: str) -> dict[str, Any]:
    for tc in state.tool_calls:
        if tc.tool == tool_name and tc.ok and isinstance(tc.output, dict):
            return tc.output
    return {}


async def run_synthesizer(state: AgentState) -> AgentState:
    counters_out = _by_step(state, "query_counters").get("counters", [])
    counter_map = {c["id"]: c for c in counters_out}

    value_rows = _by_step(state, "compute_counter_value").get("counters", [])
    value_map = {r["counter_id"]: r for r in value_rows}

    prop_rows = _by_step(state, "predict_module_propensity").get("counters", [])
    prop_map = {r["counter_id"]: r for r in prop_rows}

    recs = _by_step(state, "recommend_modules").get("recommendations", [])
    rec_map: dict[str, dict[str, Any]] = {}
    for r in recs:
        if r["counter_id"] not in rec_map and r.get("eligible"):
            rec_map[r["counter_id"]] = r

    field_notes = _by_step(state, "search_field_notes").get("matches", [])
    citation_map: dict[str, list[str]] = {}
    for m in field_notes:
        citation_map.setdefault(m["counter_id"], []).append(m["id"])

    target_module = state.plan.target_module if state.plan else None

    # Intent-aware composite weighting:
    #   Remediation modules (reconciliation, offline sync) fix an active leak, so
    #   urgency beats counter size → propensity dominates.
    #   Growth modules favour high-value counters → balanced.
    if target_module in _REMEDIATION:
        w_value, w_prop = 0.2, 0.8
    else:
        w_value, w_prop = 0.4, 0.6

    # Rank over every counter we scored. Propensity is preferred, but if that
    # step returned nothing (e.g. no module specified) we still surface the
    # counters found by value/query so a lookup never yields an empty result.
    ranked_ids = list(prop_map) or list(value_map) or list(counter_map)

    candidates: list[CandidateRecord] = []
    for cid in ranked_ids:
        prop = prop_map.get(cid, {})
        v = value_map.get(cid, {})
        val_score = float(v.get("value_score", 0.0))
        prop_score = float(prop.get("propensity_score", 0.0))
        composite = round(w_value * val_score + w_prop * prop_score, 4)
        rec = rec_map.get(cid)
        mod_id = (rec or {}).get("module_id") or target_module or "MOD-RECON"
        mod_name = (rec or {}).get("module_name") or _MODULE_NAME.get(mod_id, mod_id)
        counter = counter_map.get(cid) or {}

        # Top features = top contributions across value + propensity
        feats = []
        for b in prop.get("breakdown", [])[:3]:
            feats.append({**b, "kind": "propensity"})
        for b in v.get("breakdown", []):
            if len(feats) >= 5:
                break
            if abs(float(b.get("contribution") or 0)) > 0.05:
                feats.append({**b, "kind": "value"})

        rationale_bits: list[str] = []
        for f in feats[:2]:
            if f.get("rationale"):
                rationale_bits.append(f["rationale"])
        rationale = " ".join(rationale_bits) or "Strong combined value + propensity signal."

        candidates.append(
            CandidateRecord(
                counter_id=cid,
                name=counter.get("name", cid),
                city=counter.get("city", ""),
                tier=counter.get("tier", ""),
                counter_type=counter.get("counter_type", ""),
                operator=counter.get("operator", ""),
                monthly_tpv=counter.get("monthly_tpv"),
                avg_daily_txns=counter.get("avg_daily_txns"),
                pending_settlement=counter.get("pending_settlement"),
                value_score=val_score,
                propensity_score=prop_score,
                composite_score=composite,
                recommended_module_id=mod_id,
                recommended_module_name=mod_name,
                top_features=feats,
                rationale=rationale,
                citations=citation_map.get(cid, []),
            )
        )

    candidates.sort(key=lambda c: c.composite_score, reverse=True)
    from app.settings import get_settings
    top_k = get_settings().agent_top_k_candidates
    candidates = candidates[:top_k]

    # Leakage + sentiment enrichment.
    #
    # Leakage risk is computed from transaction evidence — settlement mismatch,
    # cash-share spike, void-and-reissue, receipt gap — and NOT from whether someone
    # happened to complain. A counter can leak quietly with a spotless support history,
    # which is exactly the case a complaint-driven system misses.
    from app.infrastructure.datasource import get_datasource
    from app.scoring.sentiment import analyze_sentiment

    ds = get_datasource()
    cand_ids = [c.counter_id for c in candidates]
    try:
        notes_map = await ds.get_field_notes_bulk(cand_ids)
    except Exception:  # noqa: BLE001
        notes_map = {}
    try:
        txn_map = await ds.get_transactions_bulk(cand_ids)
    except Exception:  # noqa: BLE001
        txn_map = {}

    for c in candidates:
        notes = notes_map.get(c.counter_id, [])
        s = analyze_sentiment(notes)
        c.sentiment = s["sentiment"]
        c.escalate = s["escalate"]

        risk, risk_feats = compute_leakage_risk(
            counter_map.get(c.counter_id) or {},
            txn_map.get(c.counter_id, []),
            notes,
        )
        c.leakage_risk = risk
        c.leakage_band = severity_band(risk)
        c.leakage_features = [b.model_dump() for b in risk_feats if b.contribution > 0]

        c.opportunity_value = _estimate_opportunity(c.recommended_module_id, c.monthly_tpv)
        c.next_action, c.priority = _next_action(c)

    # Re-rank so the action queue leads with what needs a human today: priority first,
    # then severity of leakage, then commercial fit.
    candidates.sort(key=lambda c: (c.priority, -c.leakage_risk, -c.composite_score))
    state.candidates = candidates

    # Emit candidate events progressively for the UI
    for c in candidates:
        state.emit(TraceEvent(event="candidate", data=c.model_dump()))

    # No candidates → return a clear, honest message instead of asking the LLM
    # to summarise an empty list (which previously produced a confusing meta-reply).
    if not candidates:
        module = (state.plan.target_module if state.plan else None) or "the requested module"
        state.final_summary = (
            f"I couldn't find counters matching that request for {module}. "
            "Try loosening the criteria — e.g. a different city, a lower TPV "
            "threshold, or dropping the counter-type filter."
        )
        state.emit(TraceEvent(event="synth", data={"summary": state.final_summary, "candidate_count": 0}))
        return state

    # LLM summary
    router = get_llm_router()
    context_for_llm = "\n".join(
        f"- {c.name} ({c.city}, {c.tier} {c.counter_type}) — composite {c.composite_score:.2f}, "
        f"module: {c.recommended_module_name}, est. annual take-rate value {_fmt_inr(c.opportunity_value) or 'n/a'}, "
        f"action: {c.next_action}; top signal: "
        f"{(c.top_features[0]['rationale'] if c.top_features else 'value+propensity composite')}"
        for c in candidates[:5]
    )
    resp = await router.complete(
        kind="reasoning",
        messages=[
            LLMMessage(role="system", content=_SYS),
            LLMMessage(role="user", content=f"Area Manager asked: {state.manager_query}\n\nCandidate counters:\n{context_for_llm}"),
        ],
        temperature=0.4,
        max_tokens=320,
    )
    text = resp.text.strip()
    route = resp.meta.get("route_used", resp.provider)
    # Never surface generic filler: if the LLM is unavailable (mock) or returns
    # nothing, build a specific, data-grounded summary from the real candidates.
    if route == "mock" or len(text) < 20:
        text = _fallback_summary(candidates)
    state.final_summary = text
    state.emit(TraceEvent(
        event="synth",
        data={"summary": state.final_summary, "candidate_count": len(candidates)},
        llm_route=route,
        latency_ms=resp.latency_ms,
        fallback_reason=resp.meta.get("fallback_reason"),
    ))
    return state


def _estimate_opportunity(module_id: str, monthly_tpv: float | None) -> float | None:
    """Indicative annual take-rate value (₹) of putting this module live on this counter.

    monthly TPV x module take rate x 12. Used only to help the Area Manager
    prioritise the queue — it is never a commercial quote.
    """
    tpv = float(monthly_tpv or 0)
    if not tpv:
        return None
    rate = _TAKE_RATE.get(module_id or "", 0.5)
    return round(tpv * (rate / 100.0) * 12, -3)


def _next_action(c: CandidateRecord) -> tuple[str, int]:
    """Concrete next step + priority (1 = act now ... 3 = nurture)."""
    if c.leakage_risk >= ESCALATION_THRESHOLD:
        return f"Call the supervisor within 48h — {c.leakage_band} revenue leakage", 1
    if c.escalate:
        return "Call the supervisor within 48h — unresolved issue on file", 1
    if c.propensity_score >= 0.6:
        return "Message the supervisor today — strong module fit", 1
    if c.propensity_score >= 0.4:
        return "Visit this counter this week", 2
    return "Add to the monthly review list", 3


def _fmt_inr(v: float | None) -> str:
    if not v:
        return ""
    if v >= 10_000_000:
        return f"~₹{v / 10_000_000:.1f}Cr"
    if v >= 100_000:
        return f"~₹{v / 100_000:.1f}L"
    return f"~₹{v / 1_000:.0f}k"


def _fallback_summary(candidates: list[CandidateRecord]) -> str:
    top = candidates[:3]
    lines: list[str] = []
    for c in top:
        signal = (c.top_features[0].get("rationale") if c.top_features else "") or "strong value and propensity"
        opp = _fmt_inr(c.opportunity_value)
        opp_clause = f" ({opp}/yr take-rate value)" if opp else ""
        lines.append(
            f"{c.name} ({c.city}) — {c.recommended_module_name}{opp_clause}: {signal} "
            f"→ {c.next_action}"
        )
    flagged = [
        f"{c.name} ({c.leakage_band}, {c.leakage_risk:.0%})"
        for c in candidates
        if c.leakage_risk >= ESCALATION_THRESHOLD
    ]
    body = "Your priority counters:\n- " + "\n- ".join(lines)
    if flagged:
        body += f"\nLeakage watch: {', '.join(flagged[:3])}."
    body += "\nEach has an explainable score and a ready-to-send WhatsApp nudge on the right."
    return body
