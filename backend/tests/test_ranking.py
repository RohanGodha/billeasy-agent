"""Golden ranking — the queue order is the product, so protect it from silent drift.

`weights.yaml` is designed to be tuned without touching code. The flip side is that a
one-line weight edit silently reorders the action queue an Area Partner Manager works
from, and nothing else in the suite would notice: the other tests assert membership
("CTR-0001 is somewhere in the ten"), never rank.

Two kinds of assertion here, deliberately separated:

* **Invariants** — properties that must hold for any sane weighting. These should never
  need re-blessing, and a failure here is a real bug.
* **Golden values** — the concrete top-N for the canonical demo query under the current
  weights. A failure here is *informational*: if you changed `weights.yaml` on purpose,
  re-bless the list. If you did not, something reordered the queue behind your back.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANONICAL_QUERY = (
    "Find ferry and bus counters in Mumbai leaking digital ticket revenue this month "
    "and draft WhatsApp nudges for the depot supervisors."
)

# Second golden: a bilingual GST ask. Same deterministic scoring pipeline — a retail
# receipts-and-GST sweep must land on the same blessed order twice in a row.
GST_QUERY = (
    "Mumbai me retail counters dhoondo jinke paas GST bills aur receipt issue hain — "
    "GST invoice receipt gap."
)

# Golden top-5 for CANONICAL_QUERY under the current weights, deterministic seed.
# Re-bless deliberately, never reflexively.
GOLDEN_TOP_5 = ["CTR-0306", "CTR-0001", "CTR-0107", "CTR-0255", "CTR-0286"]

GOLDEN_GST_TOP_3 = ["CTR-0396", "CTR-0201", "CTR-0084"]

# Each hand-built hero must surface its intended module through real scoring.
HERO_MODULE = {
    "CTR-0001": "MOD-RECON",     # ferry: cash spike + void/reissue
    "CTR-0002": "MOD-OFFLINE",   # bus: 240 min peak downtime
    "CTR-0003": "MOD-LOYALTY",   # retail: high TPV, no loyalty module
    "CTR-0004": "MOD-ETICKET",   # metro: NCMC share only 8%
    "CTR-0005": "MOD-BILLING",   # retail: 46% receipt-issuance gap
}


async def run() -> int:
    import yaml

    from app.agent import AgentState, run_agent
    from app.db.sqlite_engine import bootstrap
    from app.infrastructure.datasource import get_datasource
    from app.scoring.leakage import _WEIGHTS_PATH, ESCALATION_THRESHOLD, severity_band
    from app.scoring.propensity import predict_propensity

    bootstrap()

    weights_raw = yaml.safe_load(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    leaks = weights_raw["leakage"]

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    async def run_candidates(query: str) -> list:
        st = AgentState(manager_query=query)
        async for _ in run_agent(st):
            pass
        return st.candidates

    # --- Weight invariants (never need re-blessing) ----------------------------
    check(
        "leakage weights sum to 1.0 — the 0-1 'share of evidence' reading stays honest",
        abs(sum(leaks.values()) - 1.0) < 1e-9,
        f"sum={sum(leaks.values()):.6f}",
    )
    check(
        "no negative leakage weights — a signal cannot reduce estimated leakage",
        all(v >= 0.0 for v in leaks.values()),
    )

    state = AgentState(manager_query=CANONICAL_QUERY)
    async for _ in run_agent(state):
        pass
    cands = state.candidates
    check("canonical query returns candidates", len(cands) >= 5, f"got {len(cands)}")
    if len(cands) < 5:
        print(f"\nRanking test FAILED: {failures}")
        return 1

    print("\n  ranking:")
    for i, c in enumerate(cands[:6], 1):
        print(f"    {i}. {c.counter_id}  {c.name[:30]:30} prio={c.priority} "
              f"leak={c.leakage_risk:.3f} ({c.leakage_band}) comp={c.composite_score:.3f}")
    print()

    # --- Invariants -----------------------------------------------------------
    keys = [(c.priority, -c.leakage_risk, -c.composite_score) for c in cands]
    check("queue is ordered by (priority, leakage, composite)", keys == sorted(keys),
          "the panel and the summary would disagree")

    check(
        "every leakage score is a float in [0,1]",
        all(isinstance(c.leakage_risk, float) and 0.0 <= c.leakage_risk <= 1.0 for c in cands),
    )
    check(
        "every band matches its score",
        all(c.leakage_band == severity_band(c.leakage_risk) for c in cands),
    )
    check(
        "anything at or above the escalation threshold is priority 1",
        all(c.priority == 1 for c in cands if c.leakage_risk >= ESCALATION_THRESHOLD),
    )
    check(
        "the query's filters held — only Mumbai ferry/bus counters",
        {c.city for c in cands} == {"Mumbai"} and {c.counter_type for c in cands} <= {"ferry", "bus"},
        f"cities={sorted({c.city for c in cands})} types={sorted({c.counter_type for c in cands})}",
    )

    # A leakage sweep must lead with a counter that actually shows leakage.
    check(
        "the top counter carries real leakage evidence",
        cands[0].leakage_risk >= 0.25 and bool(cands[0].leakage_features),
        f"leak={cands[0].leakage_risk:.3f}",
    )

    # --- Hero → module mapping (semantic, and the one that matters most) -------
    ds = get_datasource()
    ids = list(HERO_MODULE)
    rows = await ds.get_counters_bulk(ids)
    txns = await ds.get_transactions_bulk(ids)
    notes = await ds.get_field_notes_bulk(ids)
    holds = await ds.get_holdings_bulk(ids)
    modules = list({m for m in HERO_MODULE.values()} | {
        "MOD-QR", "MOD-WA-RECEIPT", "MOD-ANALYTICS", "MOD-BILLING",
        "MOD-LOYALTY", "MOD-ETICKET", "MOD-OFFLINE", "MOD-RECON",
    })
    for cid, expected in HERO_MODULE.items():
        scored = sorted(
            ((m, predict_propensity(rows[cid], txns.get(cid, []), holds.get(cid, []),
                                    notes.get(cid, []), m)[0]) for m in modules),
            key=lambda x: -x[1],
        )
        got, score = scored[0]
        check(f"{cid} surfaces {expected}", got == expected,
              f"got {got} ({score:.3f}), runner-up {scored[1][0]} ({scored[1][1]:.3f})")

    # --- Golden values (informational failure) --------------------------------
    top5 = [c.counter_id for c in cands[:5]]
    if top5 != GOLDEN_TOP_5:
        print()
        print("  [FAIL] golden top-5 changed")
        print(f"         expected {GOLDEN_TOP_5}")
        print(f"         actual   {top5}")
        print("         If you edited weights.yaml or the seeder on purpose, re-bless")
        print("         GOLDEN_TOP_5 above. If you did not, the queue reordered on its own.")
        failures.append("golden top-5 changed")
    else:
        print(f"  [ok] golden top-5 unchanged - {top5}")

    # --- Second golden: the bilingual GST ask ---------------------------------
    gst = await run_candidates(GST_QUERY)
    check("GST query returns candidates", len(gst) >= 3, f"got {len(gst)}")
    if len(gst) >= 3:
        check(
            "GST sweep stays within the requested scope",
            {c.city for c in gst} == {"Mumbai"} and {c.counter_type for c in gst} <= {"retail"},
            f"cities={sorted({c.city for c in gst})} types={sorted({c.counter_type for c in gst})}",
        )
        print("\n  GST ranking:")
        for i, c in enumerate(gst[:3], 1):
            print(f"    {i}. {c.counter_id}  {c.name[:30]:30} prio={c.priority} "
                  f"leak={c.leakage_risk:.3f} ({c.leakage_band}) comp={c.composite_score:.3f}")
        print()
        gst_top = [c.counter_id for c in gst[:3]]
        if gst_top != GOLDEN_GST_TOP_3:
            print()
            print("  [FAIL] golden GST top-3 changed")
            print(f"         expected {GOLDEN_GST_TOP_3}")
            print(f"         actual   {gst_top}")
            print("         If you edited weights.yaml or the seeder on purpose, re-bless")
            print("         GOLDEN_GST_TOP_3 above. If you did not, the queue reordered on its own.")
            failures.append("golden GST top-3 changed")
        else:
            print(f"  [ok] golden GST top-3 unchanged - {gst_top}")

    if failures:
        print(f"\nRanking test FAILED: {failures}")
        return 1
    print("\nRanking tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
