"""FAQ intent routing — capability questions must answer from the knowledge pack,
not run the counter-scoring pipeline."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def run() -> int:
    from app.agent import AgentState, run_agent
    from app.agent.knowledge import CAPABILITIES, FAQS
    from app.db.sqlite_engine import bootstrap

    bootstrap()
    print(f"FAQ count: {len(FAQS)} | capabilities: {len(CAPABILITIES)}")
    assert len(FAQS) >= 50, f"expected >=50 FAQs, got {len(FAQS)}"

    async def t(q: str) -> AgentState:
        s = AgentState(manager_query=q)
        async for _ in run_agent(s):
            pass
        return s

    for q in [
        "List 10 things you can help me with",
        "What Billeasy modules can you recommend?",
        "Who are you?",
    ]:
        s = await t(q)
        print(f"\n{q!r}\n  intent={s.intent} cands={len(s.candidates)}\n  reply={s.final_summary[:160]}")
        assert s.intent == "faq", f"expected faq, got {s.intent}"
        assert len(s.candidates) == 0, "a capability question must not run the scoring pipeline"
        assert s.final_summary.strip(), "empty FAQ reply"

    print("\nFAQ routing test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
