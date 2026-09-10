"""End-to-end smoke test of the SQLite + tools + scoring layers.

Runs keyless against the deterministic mock LLM and the seeded counter network.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Allow `python tests\test_smoke.py` style direct runs
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.application.tool_registry import get_registry, invoke_tool
    from app.db.sqlite_engine import bootstrap

    print(">>> Bootstrapping SQLite + seeding...")
    bootstrap()

    print(">>> Registering tools...")
    reg = get_registry()
    expected = {
        "query_counters", "get_counter_transactions", "compute_counter_value",
        "predict_module_propensity", "recommend_modules", "search_field_notes",
        "generate_whatsapp_message", "create_outreach_batch",
        "diagnose_reconciliation", "validate_invoice_layout",
        "analyze_telemetry", "generate_erp_mapping",
    }
    missing = expected - set(reg.keys())
    assert not missing, f"missing tools: {missing}"
    print(f"    OK - {len(reg)} tools registered: {sorted(reg.keys())}")

    print(">>> query_counters (Mumbai ferry + bus)...")
    res = asyncio.run(invoke_tool("query_counters", {
        "cities": ["Mumbai"], "counter_types": ["ferry", "bus"], "limit": 25,
    }))
    assert res["ok"], res
    data = res["data"]
    print(f"    OK - source={data['source']}, rows={data['rows']}")
    assert data["rows"] >= 1, "Expected at least Gateway Jetty"
    ids = [c["id"] for c in data["counters"]]
    assert "CTR-0001" in ids, f"Gateway Jetty not in results: {ids[:8]}"
    # Geographic coherence: a Mumbai filter must not leak other cities in.
    cities = {c["city"] for c in data["counters"]}
    assert cities == {"Mumbai"}, f"city filter leaked: {cities}"
    types = {c["counter_type"] for c in data["counters"]}
    assert types <= {"ferry", "bus"}, f"counter_type filter leaked: {types}"
    print(f"    Gateway Jetty at position {ids.index('CTR-0001') + 1}; cities={cities}")

    print(">>> query_counters relaxation note (strict filter dropping a threshold)...")
    res = asyncio.run(invoke_tool("query_counters", {
        "cities": ["Mumbai"], "min_tpv": 10**12,
    }))
    assert res["ok"], res
    relaxed = res["data"]["relaxed_filters"]
    note = res["data"]["relaxation_note"]
    print(f"    OK - dropped {relaxed}; note: {note}")
    assert "min_tpv" in relaxed, f"expected min_tpv dropped, got {relaxed}"
    assert note and "minimum-TPV filter" in note and "wider sweep" in note, f"note missing: {note}"

    print(">>> compute_counter_value...")
    res = asyncio.run(invoke_tool("compute_counter_value", {"counter_ids": ids[:20]}))
    assert res["ok"], res
    print("    OK - top 3 value scores: " + ", ".join(
        f"{c['counter_id']}={c['value_score']:.2f}" for c in res["data"]["counters"][:3]))

    print(">>> predict_module_propensity (MOD-RECON)...")
    res = asyncio.run(invoke_tool("predict_module_propensity", {
        "counter_ids": ["CTR-0001", "CTR-0002", "CTR-0003"],
        "module_id": "MOD-RECON",
    }))
    assert res["ok"], res
    scores = {c["counter_id"]: c["propensity_score"] for c in res["data"]["counters"]}
    print(f"    OK - scores: {scores}")
    assert scores["CTR-0001"] >= 0.5, f"Gateway Jetty MOD-RECON should be >=0.5: {scores['CTR-0001']}"
    # The leaking ferry counter must outrank the healthy retail one for reconciliation.
    assert scores["CTR-0001"] > scores["CTR-0003"], "leaking counter should outrank healthy one"

    print(">>> recommend_modules for the metro TVM cluster (expecting e-ticketing)...")
    res = asyncio.run(invoke_tool("recommend_modules", {"counter_ids": ["CTR-0004"], "top_k": 2}))
    assert res["ok"], res
    recs = res["data"]["recommendations"]
    print("    OK - top recs: " + ", ".join(
        f"{r['module_id']} ({r['propensity_score']:.2f})" for r in recs))
    assert recs and recs[0]["module_id"] == "MOD-ETICKET", f"expected MOD-ETICKET, got {recs[0]}"

    print(">>> get_counter_transactions (leakage aggregates for Gateway Jetty)...")
    res = asyncio.run(invoke_tool("get_counter_transactions", {"counter_id": "CTR-0001"}))
    assert res["ok"], res
    agg = res["data"]["aggregates"]
    mismatch = (agg["total_collected"] - agg["total_settled"]) / agg["total_collected"]
    print(f"    OK - collected={agg['total_collected']:.0f} settled={agg['total_settled']:.0f} "
          f"cash_share={agg['cash_share']:.2f} voids={agg['void_reissue_count']} "
          f"mismatch={mismatch:.1%}")
    assert agg["void_reissue_count"] >= 1, "expected the void/reissue pattern"
    assert mismatch > 0.02, f"expected a settlement mismatch on the leaking counter: {mismatch:.3f}"

    print(">>> generate_whatsapp_message for Gateway Jetty (mock LLM)...")
    res = asyncio.run(invoke_tool("generate_whatsapp_message", {
        "counter_id": "CTR-0001",
        "module_id": "MOD-RECON",
        "tone": "professional",
        "top_features": [],
        "manager_name": "Rohan",
    }))
    assert res["ok"], res
    # DPDP consent gate: Gateway Jetty is opted out, so the tool must refuse to draft.
    assert res["data"]["compliance"]["ok"] is False, res["data"]["compliance"]
    assert res["data"]["compliance"]["error"] == "dpdp_consent_required", res["data"]["compliance"]
    print("    OK - refused: no DPDP consent on file")

    print(">>> generate_whatsapp_message for a consented counter (Wadala Depot)...")
    res = asyncio.run(invoke_tool("generate_whatsapp_message", {
        "counter_id": "CTR-0002",
        "module_id": "MOD-OFFLINE",
        "tone": "professional",
        "top_features": [],
        "manager_name": "Rohan",
    }))
    assert res["ok"], res
    msg = res["data"]["message"]
    print(f"    OK - message ({len(msg)} chars): {msg[:120]}...")
    print(f"    compliance.ok = {res['data']['compliance']['ok']}")
    assert res["data"]["compliance"]["ok"] is True, res["data"]["compliance"]
    assert res["data"]["compliance"].get("dpdp_consent_ok") is True, res["data"]["compliance"]

    print("\nAll smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
