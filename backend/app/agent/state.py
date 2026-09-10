"""Agent state — pure Pydantic, JSON-serialisable, stored verbatim in `agent_traces`."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    step: int
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    expected: str = ""
    done: bool = False


class Plan(BaseModel):
    intent: str = ""
    target_module: str | None = None
    city_filter: list[str] | None = None
    tone: str = "professional"
    language: str = "English"          # target language for outreach drafts
    steps: list[PlanStep] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    step: int
    tool: str
    args: dict[str, Any]
    ok: bool
    source: str | None = None
    latency_ms: int = 0
    output: Any = None
    error: str | None = None


class TraceEvent(BaseModel):
    """One event in the agent's reasoning timeline. SSE-friendly."""
    event: Literal[
        "plan", "router", "tool_call", "tool_result", "critic", "synth",
        "candidate", "draft", "token", "final", "error", "info",
    ]
    ts: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    data: dict[str, Any] = Field(default_factory=dict)
    llm_route: str | None = None
    latency_ms: int | None = None
    fallback_reason: str | None = None


class CandidateRecord(BaseModel):
    counter_id: str
    name: str
    city: str
    tier: str
    counter_type: str = ""
    operator: str = ""                  # merchant / transit agency running the counter
    monthly_tpv: float | None = None
    avg_daily_txns: float | None = None
    pending_settlement: float | None = None
    value_score: float
    propensity_score: float
    composite_score: float
    recommended_module_id: str
    recommended_module_name: str
    top_features: list[dict[str, Any]]
    rationale: str
    citations: list[str] = Field(default_factory=list)
    # Sentiment / leakage-risk from field-visit notes
    sentiment: str = "neutral"          # positive | neutral | negative
    escalate: bool = False              # flag for priority human attention
    # Revenue slipping off the digital rail: 0-1 severity, not a flag. Computed from
    # transaction evidence (mismatch, cash spike, void/reissue...) by scoring/leakage.py,
    # with the same per-feature audit trail as every other score in the system.
    leakage_risk: float = 0.0
    leakage_band: str = "clear"         # clear | watch | elevated | severe
    leakage_features: list[dict[str, Any]] = Field(default_factory=list)
    # Action layer: estimated opportunity size and the concrete next step
    opportunity_value: float | None = None
    next_action: str = ""
    priority: int = 3                   # 1 = act now, 3 = nurture


class DraftRecord(BaseModel):
    counter_id: str
    module_id: str
    message: str
    compliance: dict[str, Any] = Field(default_factory=dict)
    llm_route: str = ""


class AgentState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    manager_query: str = ""
    manager_name: str = "Rohan"

    # Conversation memory: prior turns [{role, content}] loaded from the session.
    history: list[dict[str, str]] = Field(default_factory=list)
    intent: str = "task"          # task | follow_up | faq | chitchat | out_of_scope
    rewritten_query: str | None = None  # set when a follow_up is expanded

    plan: Plan | None = None
    cursor: int = 0
    iterations: int = 0
    replans: int = 0

    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    candidates: list[CandidateRecord] = Field(default_factory=list)
    drafts: list[DraftRecord] = Field(default_factory=list)

    final_summary: str = ""
    error: str | None = None
    events: list[TraceEvent] = Field(default_factory=list)
    # `archive` accumulates every event for the whole run and is never drained,
    # so the Responder can persist the complete trace even though `events` is
    # drained incrementally for SSE streaming.
    archive: list[TraceEvent] = Field(default_factory=list)

    def emit(self, ev: TraceEvent) -> None:
        self.events.append(ev)
        self.archive.append(ev)

    def scratchpad(self) -> dict[str, Any]:
        """Lightweight view of recent tool outputs the LLM can consume."""
        return {
            "manager_query": self.manager_query,
            "plan": self.plan.model_dump() if self.plan else None,
            "completed_steps": [
                {"step": tc.step, "tool": tc.tool, "ok": tc.ok, "source": tc.source}
                for tc in self.tool_calls
            ],
            "candidate_count": len(self.candidates),
        }
