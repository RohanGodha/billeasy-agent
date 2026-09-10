"""Field-note sentiment / escalation enrichment + multilingual draft routing."""
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
    from app.db.sqlite_engine import bootstrap
    from app.infrastructure.datasource import get_datasource
    from app.scoring.sentiment import analyze_sentiment

    bootstrap()
    ds = get_datasource()

    # CTR-0002 (BEST Depot, Wadala) has device-down / connectivity notes -> negative.
    wadala = await ds.get_field_notes("CTR-0002")
    s = analyze_sentiment(wadala.data or [])
    print(f"Wadala  -> sentiment={s['sentiment']} escalate={s['escalate']} signals={s['signals']}")
    assert s["sentiment"] == "negative", f"expected negative, got {s['sentiment']}"
    assert s["escalate"] is True
    # Sentiment must NOT emit a leakage score — that comes from transaction evidence
    # in scoring/leakage.py. Two different things called leakage_risk is a trap.
    assert "leakage_risk" not in s, "sentiment should not produce a leakage score"

    # CTR-0003 (Sahakari Bhandar, Dadar) is a healthy retail counter -> not escalated.
    dadar = await ds.get_field_notes("CTR-0003")
    sd = analyze_sentiment(dadar.data or [])
    print(f"Dadar   -> sentiment={sd['sentiment']} escalate={sd['escalate']}")
    assert sd["escalate"] is False

    # Multilingual routing through the full agent.
    from app.agent import AgentState, run_agent

    state = AgentState(
        manager_query=(
            "Which retail outlets crossed the GST e-invoice threshold but aren't "
            "issuing compliant bills? Draft the messages in Hindi."
        )
    )
    async for _ in run_agent(state):
        pass
    print(f"\nPlan language: {state.plan.language}")
    assert state.plan.language == "Hindi", f"expected Hindi, got {state.plan.language}"

    escalated = [c for c in state.candidates if c.escalate]
    print(f"Candidates: {len(state.candidates)}  escalated: {len(escalated)}")
    for c in state.candidates[:5]:
        print(f"  {c.name[:30]:30} sentiment={c.sentiment:8} escalate={c.escalate} "
              f"leak={c.leakage_risk:.2f} ({c.leakage_band})")

    print("\nSentiment + multilingual test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
