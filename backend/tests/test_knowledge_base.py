"""Knowledge base: human-language questions over the payments/compliance corpus and
over live counter records."""
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
    from app.knowledge_base import get_knowledge_base

    bootstrap()
    kb = get_knowledge_base()
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        status = "ok" if cond else "FAIL"
        print(f"  [{status}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    # 1. Document grounding over the payments / compliance corpus.
    r = await kb.ask("What is the GST e-invoicing turnover threshold?")
    check("gst threshold returns an answer", len(r["answer"]) > 10, r["answer"][:70])
    check("gst threshold cites a document", len(r["sources"]) > 0, str(r["sources"]))

    r = await kb.ask("When does Billeasy settle money to the merchant?")
    check("settlement/T+1 answered", len(r["answer"]) > 10, r["answer"][:70])

    r = await kb.ask("What is NCMC and how does it work at an AFC gate?")
    check("ncmc answered", len(r["answer"]) > 10, r["answer"][:70])

    # 2. Live counter grounding: a named counter resolves to its own record.
    for phrasing in [
        "What modules does Gateway Jetty run?",
        "Tell me about Gateway Jetty Counter 3",
        "What is the pending settlement at Gateway Jetty?",
    ]:
        r = await kb.ask(phrasing)
        resolved = "Counter Record" in r["sources"]
        check(f"counter resolved: '{phrasing[:38]}'", resolved, str(r["sources"]))
        check(f"counter answer non-empty: '{phrasing[:30]}'", len(r["answer"]) > 10)

    # 3. A counter that does NOT run a module must be reported truthfully, not invented.
    r = await kb.ask("Does Sahakari Bhandar Dadar run the loyalty module?")
    check("dadar resolved", "Counter Record" in r["sources"], str(r["sources"]))
    print(f"        answer: {r['answer'][:160]}")

    # 4. Generic question with no named counter -> falls back to documents.
    r = await kb.ask("What is zero MDR and which instruments does it apply to?")
    check("generic mdr answered", len(r["answer"]) > 10, str(r["sources"]))
    check("generic question resolves no counter", "Counter Record" not in r["sources"],
          str(r["sources"]))

    # 5. Sources endpoint surface
    srcs = kb.sources()
    check("eight knowledge sources loaded", len(srcs) == 8, str([s["source"] for s in srcs]))

    # 6. Main-chat routing: knowledge questions to the KB, actions to the pipeline.
    from app.agent.nodes.intent import _heuristic
    routes = {
        "what is the GST e-invoice threshold": "knowledge",
        "how does NCMC settlement work": "knowledge",
        "how does merchant KYC work": "knowledge",
        "find ferry counters leaking revenue and draft messages": "task",
        "show me counters with a settlement mismatch": "task",
        "what can you do": "faq",
        "hi there": "chitchat",
        "write a poem about Mumbai": "out_of_scope",
        "which ERP can we map our accounting to": "knowledge",
        "how do I use the API endpoints": "knowledge",
        "what is our PII data-protection posture": "knowledge",
    }
    for q, expected in routes.items():
        got = _heuristic(q, False)
        check(f"route '{q[:36]}' -> {expected}", got == expected, f"got {got}")

    if failures:
        print(f"\nKnowledge base test FAILED: {failures}")
        return 1
    print("\nKnowledge base test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
