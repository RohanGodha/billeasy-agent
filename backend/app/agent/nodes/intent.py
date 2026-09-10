"""Intent gate — classifies the Area Manager's message into a route before any work.

Routes: task | follow_up | faq | chitchat | out_of_scope

Strategy: a fast heuristic first pass, upgraded by an LLM classifier
(INTENT_PROMPT) whenever a real provider is configured. Conversation history is
considered so refinements are recognised as follow_ups.
"""
from __future__ import annotations

import re

from app.agent.prompts import CHITCHAT_PROMPT, GUARDRAIL_PROMPT, INTENT_PROMPT, SYSTEM_PROMPT
from app.agent.state import AgentState, TraceEvent
from app.infrastructure.llm import LLMMessage, get_llm_router

_TASK_PATTERNS = re.compile(
    r"\b(find|show|list|identify|pull|get|counters?|outlets?|jetty|jetties|depots?|"
    r"stations?|merchants?|module|propensity|adopt|outreach|whatsapp|message|nudge|campaign|"
    r"leak(age|ing)?|mismatch|shortfall|tier|anchor|flagship|cross[- ]?sell|upsell|"
    r"recommend|score|target|portfolio|network)\b",
    re.IGNORECASE,
)
_FOLLOWUP_PATTERNS = re.compile(
    r"^\s*(now|also|instead|just|only|then|and|but|make (it|them)|narrow|"
    r"filter|exclude|include|top \d+|change|warmer|formal|shorter|longer|"
    r"more|less|same but)\b",
    re.IGNORECASE,
)
# Continuation phrasing that points back at the result set just produced — "which of
# those", "of the counters you found", "the strongest". Meaningless on a fresh thread,
# so every branch is guarded by has_history; the query is a refinement of the prior run,
# not a brand-new sweep.
_FOLLOWUP_CONTINUATION = re.compile(
    r"\bwhich\s+(of|one)\b|\bwhat about\b|\bhow about\b|\band\s+(then|also)\b|"
    r"\bof\s+(those|these|them)\b|\b(the|these|those)\s+\w+\s+(you|we)\s+"
    r"(found|flagged|listed|shortlisted|recommended|looked\s+at|uncovered|scanned)\b|"
    r"\bthe\s+(strongest|biggest|largest|top(?!\s+\d+)|best|worst)\b|\bwith the\s+"
    r"(strongest|biggest|largest|highest|most|least)\b|\b(first|second|third|next|last)\s+"
    r"(one|item|result|counter|outlet|run)\b",
    re.IGNORECASE,
)
_GREETING_PATTERNS = re.compile(
    r"^\s*(hi|hey|hello|yo|hola|namaste|good (morning|afternoon|evening)|"
    r"sup|what'?s up|how are you|thanks?|thank you|ok(ay)?|cool|nice|bye|goodbye)"
    r"(\s+(there|team|copilot|counter|rohan|buddy|mate|all))?\s*[!.?]*\s*$",
    re.IGNORECASE,
)
_FAQ_PATTERNS = re.compile(
    r"(who are you|what (is|are|can) (this|you)|what do you do|how do you|"
    r"what data|which modules?|can you|do you (send|support)|help\b|capabilit)",
    re.IGNORECASE,
)
_OUT_OF_SCOPE = re.compile(
    r"\b(weather|poem|joke|code|python|football|cricket score|movie|recipe|"
    r"translate|stock price|news)\b",
    re.IGNORECASE,
)
# Whole-message control commands. Anchored to a bare keyword so "help me find counter X"
# (a real task) never matches — the message must BE the command, not contain it.
_COMMAND_PATTERNS = re.compile(
    r"^\s*(help|back|go\s+back|cancel|stop|reset|restart|start\s+over|start\s+again|"
    r"clear\s+(the\s+)?(session|conversation|chat(\s+history)?|history))\s*[.!?]*\s*$",
    re.IGNORECASE,
)
# Action verbs that mean "run the counter pipeline" — these win over knowledge.
_ACTION_PATTERNS = re.compile(
    r"\b(find|identify|pull|shortlist|target|draft|generate|score|rank|flag|"
    r"recommend|outreach|campaign|nudge|cross[- ]?sell|upsell)\b",
    re.IGNORECASE,
)
# Informational payments / ticketing questions answerable from the reference KB.
_KNOWLEDGE_PATTERNS = re.compile(
    r"\b(rbi|payment aggregator|payment gateway|nodal|escrow|gst|e-?invoic|irn|hsn|"
    r"credit note|mdr|interchange|upi|rupay|ncmc|one nation one card|afc|"
    r"t\+1|t\+2|settlement (cycle|norm|window)|chargeback|dispute|kyc|ckyc|v-?cip|"
    r"dpdp|consent|take rate|threshold|eligibilit|"
    r"erp|tally|zoho|sap b1|ledger|accounting|integration|api|webhook|sdk|"
    r"endpoint|security|pii|privacy|audit|data protection|encryption|redact|mask(ing)?|"
    r"soc ?2|gdpr?|breach|erasure|retention|"
    r"error codes?|gateway (timeout|decline|error)|refund policy|"
    r"how (do|to|does) .*(onboard|settle|kyc|reconcile)|documents? (needed|required)|process of)\b",
    re.IGNORECASE,
)
_PERSONA_HISTORY = re.compile(
    r"\b(past|previous|existing|active|current|live)\s+(modules?|settlements?)\b"
    r"|\bmodules?\s+(live|running|held|by|of|for|does)\b"
    r"|\bwhat\s+modules?\b"
    r"|'s\s+(module|modules|settlement|payout|holdings?|counter|tpv|history|transactions?|field notes?)\b"
    r"|\b(settlement|payout|module|holdings?|counter|tpv|transaction|field note)s?\s+(history|record|details?)\b",
    re.IGNORECASE,
)
# A plural counter noun means "sweep the network", even when the ask also mentions
# a compliance term ("which outlets crossed the GST threshold?") — that's a task,
# not a knowledge lookup about the rule itself.
_COUNTER_SET = re.compile(
    r"\b(counters|outlets|jetties|depots|stations|terminals|merchants|partners)\b",
    re.IGNORECASE,
)

VALID_INTENTS = {"task", "follow_up", "knowledge", "faq", "chitchat", "out_of_scope", "command"}


def _is_question_about_assistant(t: str) -> bool:
    """'what can you do', 'which modules can you recommend' → FAQ, not a task."""
    if not _FAQ_PATTERNS.search(t):
        return False
    # Phrased as a question to the assistant (mentions you/your or ends with ?)
    return bool(re.search(r"\b(you|your)\b", t, re.IGNORECASE) or t.strip().endswith("?"))


def _heuristic(text: str, has_history: bool) -> str:
    t = (text or "").strip()
    if not t:
        return "chitchat"
    if _COMMAND_PATTERNS.match(t):
        return "command"
    if _GREETING_PATTERNS.match(t):
        return "chitchat"
    if _OUT_OF_SCOPE.search(t):
        return "out_of_scope"
    # Questions ABOUT the assistant's capabilities are FAQ, even if they contain
    # task-like words ("what modules can you recommend?").
    if _is_question_about_assistant(t):
        return "faq"
    if has_history and _FOLLOWUP_PATTERNS.match(t) and not _TASK_PATTERNS.search(t):
        return "follow_up"
    # A continuation that reaches backwards into the just-produced results is a
    # follow-up even though it names counter nouns ("which of those counters ...").
    if has_history and _FOLLOWUP_CONTINUATION.search(t):
        return "follow_up"
    # Action verbs mean "run the pipeline" → task wins over knowledge.
    if _ACTION_PATTERNS.search(t):
        return "task"
    # A set-of-counters ask is a pipeline run even if it names a compliance term.
    if _COUNTER_SET.search(t):
        return "task"
    # Informational payments/compliance questions / a named counter's history → knowledge base.
    if _KNOWLEDGE_PATTERNS.search(t) or _PERSONA_HISTORY.search(t):
        return "knowledge"
    if _TASK_PATTERNS.search(t):
        if has_history and _FOLLOWUP_PATTERNS.match(t):
            return "follow_up"
        return "task"
    if _FAQ_PATTERNS.search(t):
        return "faq"
    return "faq"  # default: treat unknown as a question, not a counter hunt


async def classify_intent(state: AgentState) -> str:
    text = state.manager_query or ""
    has_history = len(state.history) > 0
    intent = _heuristic(text, has_history)

    router = get_llm_router()
    # Upgrade with the LLM classifier when any real provider exists. Checked
    # generically rather than by naming providers: this gate previously listed only
    # Gemini and Groq, so adding Anthropic silently left an Anthropic-only
    # deployment stuck on heuristic routing while Claude led every other route.
    status = router.status()
    if any(live for name, live in status.items() if name != "mock"):
        try:
            convo = "\n".join(f"{h['role']}: {h['content']}" for h in state.history[-4:])
            resp = await router.complete(
                kind="reasoning",
                messages=[
                    LLMMessage(role="system", content=INTENT_PROMPT),
                    LLMMessage(role="user", content=f"Recent conversation:\n{convo or '(none)'}\n\nNew message: {text}"),
                ],
                temperature=0.0,
                max_tokens=40,
                json_mode=True,
            )
            data = resp.json_data or {}
            cand = str(data.get("intent", "")).strip().lower()
            if cand in VALID_INTENTS:
                intent = cand
        except Exception:  # noqa: BLE001
            pass

    state.intent = intent
    state.emit(TraceEvent(event="info", data={"node": "intent", "intent": intent, "has_history": has_history}))
    return intent


async def run_chitchat(state: AgentState) -> AgentState:
    name = state.manager_name or "Rohan"
    router = get_llm_router()
    try:
        convo = "\n".join(f"{h['role']}: {h['content']}" for h in state.history[-4:])
        resp = await router.complete(
            kind="reasoning",
            messages=[
                LLMMessage(role="system", content=f"{SYSTEM_PROMPT}\n\n{CHITCHAT_PROMPT}"),
                LLMMessage(role="user", content=(
                    f"Area Manager name: {name}\n"
                    f"Recent conversation:\n{convo or '(none)'}\n\n"
                    f"Area Manager just said: {state.manager_query}"
                )),
            ],
            temperature=0.7,
            max_tokens=120,
        )
        text = resp.text.strip()
        route = resp.meta.get("route_used", resp.provider)
        fallback = resp.meta.get("fallback_reason")
    except Exception:  # noqa: BLE001
        text = (
            f"Hi {name}! I'm Counter Copilot. Tell me which counters to look at and I'll query the "
            "network, flag revenue leakage and settlement gaps, recommend the right Billeasy module, "
            "and draft WhatsApp nudges for the supervisors."
        )
        route = None
        fallback = None

    state.final_summary = text
    state.emit(TraceEvent(
        event="synth",
        data={"summary": text, "candidate_count": 0, "mode": "chitchat"},
        llm_route=route,
        fallback_reason=fallback,
    ))
    return state


async def run_guardrail(state: AgentState) -> AgentState:
    router = get_llm_router()
    try:
        resp = await router.complete(
            kind="reasoning",
            messages=[
                LLMMessage(role="system", content=SYSTEM_PROMPT + "\n\n" + GUARDRAIL_PROMPT),
                LLMMessage(role="user", content=state.manager_query),
            ],
            temperature=0.3,
            max_tokens=120,
        )
        text = resp.text.strip()
    except Exception:  # noqa: BLE001
        text = (
            "That's outside what I can help with. I'm your Billeasy counter copilot — I can find "
            "counters, flag revenue leakage and settlement mismatches, recommend the right module, "
            "and draft supervisor outreach."
        )
    state.final_summary = text
    state.emit(TraceEvent(event="synth", data={"summary": text, "candidate_count": 0, "mode": "out_of_scope"}))
    return state


async def _clear_session_memory(session_id: str) -> None:
    """Delete a session's conversational history (the messages thread).

    Traces and persisted outreach drafts are deliberately kept — they authenticate the
    run; only what follow-up decoding reads (the *messages*) is cleared, so the next
    message starts a fresh thread rather than being treated as a refinement of the old one.
    """
    from app.db.sqlite_engine import get_async_conn  # local import avoids a cycle

    async with get_async_conn() as conn:
        await conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await conn.commit()


async def run_command(state: AgentState) -> AgentState:
    """Deterministic, keyless handling of the control commands.

    `help` lists capabilities and the commands themselves; `back`/`cancel`/`stop`
    acknowledge that there is nothing running to cancel (runs complete or the stream
    drops, but never pause); `reset` clears the session's conversation memory.
    """
    t = (state.manager_query or "").strip().lower()
    mode = "help"
    if re.search(r"\breset\b|\brestart\b|start\s+over|start\s+again|clear\b", t):
        mode = "reset"
        await _clear_session_memory(state.session_id)
        state.history = []
        text = (
            "Done — cleared this session's conversation memory. Your next message will be treated "
            "as a fresh ask. Past runs and their drafts are still saved in this session."
        )
    elif re.search(r"\bback\b|\bcancel\b|\bstop\b", t):
        mode = "cancel"
        text = (
            "There's nothing running for me to cancel — the last run finished and its drafts are "
            "saved in this session. Start a new sweep whenever you're ready, or type help to see "
            "what I can do."
        )
    else:
        text = (
            "I'm Counter Copilot — your Billeasy counter revenue-assurance copilot. I find counters, "
            "flag revenue leakage and settlement mismatches, recommend the right Billeasy module, and "
            "draft compliance-checked WhatsApp nudges for supervisors.\n\n"
            "Commands: type \"help\" anytime, \"reset\" to clear this session's memory and start fresh, "
            "or \"cancel\" if a run is misbehaving. Otherwise just ask — a city, a counter type, or a "
            "signal like leakage, settlement mismatch, device downtime or GST bills."
        )

    state.final_summary = text
    state.emit(TraceEvent(event="synth", data={"summary": text, "candidate_count": 0, "mode": f"command:{mode}"}))
    return state
