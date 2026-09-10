"""Agent orchestration.

We use a hand-written deterministic async DAG rather than a runtime DAG framework for
two reasons:
  - the node sequence is fixed (Planner → loop(Executor → Critic) → Synthesizer → MessageGen → Responder),
  - it gives us tight control of SSE streaming, which is the whole UX.

There is deliberately **no orchestration framework dependency**. Each node is a plain
async function over `AgentState`, so they stay pure and reusable if a richer DAG ever
justifies one.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.agent.nodes.critic import run_critic
from app.agent.nodes.faq import run_faq
from app.agent.nodes.intent import classify_intent, run_chitchat, run_command, run_guardrail
from app.agent.nodes.knowledge import run_knowledge
from app.agent.nodes.message_generator import run_message_generator
from app.agent.nodes.planner import run_planner
from app.agent.nodes.responder import run_responder
from app.agent.nodes.synthesizer import run_synthesizer
from app.agent.nodes.tool_executor import execute_step
from app.agent.state import AgentState, TraceEvent
from app.observability import get_logger
from app.security import mask_pii
from app.settings import get_settings

logger = get_logger(__name__)


async def run_agent(state: AgentState) -> AsyncIterator[TraceEvent]:
    """Run the agent and yield TraceEvents as they are produced.

    Consumers (the SSE endpoint) emit each event to the wire immediately, so the
    UI populates the trace pane in real time.
    """
    settings = get_settings()
    # DPDP entry gate: enforce masking even for direct AgentState callers. The chat
    # boundary already masked the query, so this is a no-op there — but a caller that
    # built state directly (test harness, script) gets the same protection before any
    # node, LLM prompt, or the agent-traces persist runs.
    state.manager_query = mask_pii(state.manager_query)
    state.emit(TraceEvent(event="info", data={"msg": "agent_started", "session": state.session_id}))
    _drain(state)
    async for ev in _yield_drain(state):
        yield ev

    # 0. Intent gate — route the message before doing any work.
    intent = await classify_intent(state)
    async for ev in _yield_drain(state):
        yield ev

    # Non-pipeline routes short-circuit with a single response.
    if intent in {"chitchat", "faq", "knowledge", "out_of_scope", "command"}:
        if intent == "chitchat":
            await run_chitchat(state)
        elif intent == "faq":
            await run_faq(state)
        elif intent == "knowledge":
            await run_knowledge(state)
        elif intent == "command":
            await run_command(state)
        else:
            await run_guardrail(state)
        async for ev in _yield_drain(state):
            yield ev
        await run_responder(state)
        async for ev in _yield_drain(state):
            yield ev
        return

    # 1. Planner (handles follow_up rewriting internally using history)
    await run_planner(state)
    async for ev in _yield_drain(state):
        yield ev
    if not state.plan or not state.plan.steps:
        # Terminate the stream properly. This used to `return` after setting `state.error`
        # without emitting anything, so the SSE stream simply stopped: no `final` event,
        # and a UI left spinning with no explanation. Fail loudly and usefully instead.
        state.error = "Planner produced no steps"
        state.final_summary = (
            "I couldn't turn that into a plan I can run. Try naming what to look at — "
            "a city, a counter type (ferry, bus, metro or retail), or a signal like "
            "revenue leakage, settlement mismatch, device downtime or GST bills."
        )
        state.emit(TraceEvent(event="info", data={"error": state.error}))
        logger.warning("Planner produced no steps for query: %r", state.manager_query[:120])
        async for ev in _yield_drain(state):
            yield ev
        await run_responder(state)
        async for ev in _yield_drain(state):
            yield ev
        return

    # 2. Loop: Tool → Critic
    while state.cursor < len(state.plan.steps) and state.iterations < settings.agent_max_iterations:
        state.iterations += 1
        await execute_step(state, state.cursor)
        async for ev in _yield_drain(state):
            yield ev
        await run_critic(state)
        async for ev in _yield_drain(state):
            yield ev

    # The iteration cap can stop the loop mid-plan (a critic-forced replan consumes an
    # iteration). Synthesising from partial tool output as though the plan had completed
    # would present a narrower answer as a complete one, so say it out loud.
    if state.cursor < len(state.plan.steps):
        unrun = len(state.plan.steps) - state.cursor
        state.emit(TraceEvent(event="info", data={
            "truncated": True,
            "note": (
                f"Stopped after {state.iterations} iterations with {unrun} step(s) unrun. "
                "The results below are based on partial tool output."
            ),
        }))
        logger.warning(
            "Plan truncated: %d/%d steps run in %d iterations",
            state.cursor, len(state.plan.steps), state.iterations,
        )
        async for ev in _yield_drain(state):
            yield ev

    # 3. Synthesizer
    await run_synthesizer(state)
    async for ev in _yield_drain(state):
        yield ev

    # 4. MessageGenerator
    await run_message_generator(state)
    async for ev in _yield_drain(state):
        yield ev

    # 5. Responder
    await run_responder(state)
    async for ev in _yield_drain(state):
        yield ev


# -------------------------------------------------------------------
# Internal: incremental event drain
# -------------------------------------------------------------------

def _drain(state: AgentState) -> list[TraceEvent]:
    out = list(state.events)
    state.events.clear()
    return out


async def _yield_drain(state: AgentState):
    for ev in _drain(state):
        yield ev
