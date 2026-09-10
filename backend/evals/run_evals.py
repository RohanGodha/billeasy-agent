"""Planner evaluation harness for Counter Copilot.

Runs every case in `evals/cases.yaml` through the *real* agent (`run_agent` over a real
`AgentState`, against whichever LLM provider `LLMRouter` resolves) and grades the
resulting **plan**, not the prose.

Usage (from `backend/`):

    PYTHONPATH=. python evals/run_evals.py
    PYTHONPATH=. python evals/run_evals.py --only gst --limit 5
    PYTHONPATH=. python evals/run_evals.py --threshold 0.85

Exit code 0 when the macro-average across dimensions is >= --threshold, 1 otherwise,
2 on a harness error. See evals/README.md for what these numbers do and do not mean.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EVALS_DIR = Path(__file__).resolve().parent
ROOT = EVALS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

# --------------------------------------------------------------------------------
# Dimensions. Each is scored independently and may be N/A (None) for a given case,
# so a knowledge question is not punished for having no target module.
# --------------------------------------------------------------------------------
DIMENSIONS: list[tuple[str, str]] = [
    ("intent", "intent"),
    ("target_module", "module"),
    ("filters", "filters"),
    ("language", "lang"),
    ("candidates", "cands"),
    ("compliance", "compl"),
    ("tools", "tools"),
    ("must_surface", "surface"),
]

# Filter keys that are graded. These are exactly the structured filters accepted by
# `app/tools/query_counters.py::QueryCountersIn` (plus `exclude_modules`); `limit` is
# deliberately not graded — it is a paging knob, not an interpretation of the ask.
LIST_FILTERS = ("cities", "tiers", "counter_types", "settlement_cycles", "exclude_modules")
SCALAR_FILTERS = (
    "min_tpv", "max_tpv", "min_pending_settlement", "min_daily_txns", "max_daily_txns",
)
GRADED_FILTERS = LIST_FILTERS + SCALAR_FILTERS

PIPELINE_TOOLS = [
    "query_counters", "compute_counter_value", "predict_module_propensity",
    "recommend_modules", "search_field_notes",
]

_MISSING = object()


# --------------------------------------------------------------------------------
# Case loading
# --------------------------------------------------------------------------------
def load_cases(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = doc.get("defaults") or {}
    cases = doc.get("cases") or []
    for c in cases:
        if "id" not in c or "query" not in c:
            raise ValueError(f"Case missing id/query: {c!r}")
        c.setdefault("expect", {})
        c.setdefault("history", [])
        c.setdefault("group", "ungrouped")
        c["query"] = " ".join(str(c["query"]).split())
    return cases, defaults


# --------------------------------------------------------------------------------
# Extraction: pull the checkable shape out of a finished AgentState
# --------------------------------------------------------------------------------
def _norm(v: Any) -> str:
    return str(v).strip().lower()


def actual_filters(state: Any) -> dict[str, Any]:
    """The `query_counters` argument set the planner actually chose.

    Mirrors `tool_executor.execute_step`: a plan-level `city_filter` is backfilled into
    `cities` when step 1 did not carry it, because that is what really reaches the tool.
    """
    plan = state.plan
    if plan is None:
        return {}
    args: dict[str, Any] = {}
    for step in plan.steps:
        if step.tool == "query_counters":
            args = dict(step.args or {})
            break
    if not args.get("cities") and plan.city_filter:
        args["cities"] = list(plan.city_filter)
    return args


def observed_routes(state: Any) -> list[str]:
    seen: list[str] = []
    for ev in state.archive:
        route = ev.llm_route
        if route and route not in seen:
            seen.append(route)
    for d in state.drafts:
        if d.llm_route and d.llm_route not in seen:
            seen.append(d.llm_route)
    return seen


# --------------------------------------------------------------------------------
# Scorers — one per dimension, each returns (score|None, detail string)
# --------------------------------------------------------------------------------
def score_intent(expect: Any, state: Any) -> tuple[float | None, str]:
    if expect is _MISSING or expect is None:
        return None, ""
    allowed = {_norm(x) for x in (expect if isinstance(expect, list) else [expect])}
    got = _norm(state.intent)
    if got in allowed:
        return 1.0, got
    return 0.0, f"got={got} want={'|'.join(sorted(allowed))}"


def score_module(expect: Any, state: Any) -> tuple[float | None, str]:
    if expect is _MISSING or expect is None:
        return None, ""
    got = (state.plan.target_module if state.plan else None) or "-"
    return (1.0, got) if got == expect else (0.0, f"got={got} want={expect}")


def score_language(expect: Any, state: Any) -> tuple[float | None, str]:
    if expect is _MISSING or expect is None:
        return None, ""
    got = (state.plan.language if state.plan else None) or "-"
    return (1.0, got) if _norm(got) == _norm(expect) else (0.0, f"got={got} want={expect}")


def score_filters(expect: Any, state: Any) -> tuple[float | None, str]:
    """Set-F1 over the expected filter assertions.

    Each expected key contributes atoms. A `null` expectation ("must not be set") is a
    single atom that is satisfied only when the planner left the key unset; setting it
    counts as both a false positive and a miss, because a spurious `min_tpv` silently
    deletes counters from the answer.
    """
    if expect is _MISSING or expect is None:
        return None, ""
    got = actual_filters(state)
    tp = fp = fn = 0
    problems: list[str] = []

    for key, want in expect.items():
        if key not in GRADED_FILTERS:
            raise ValueError(f"cases.yaml grades unknown filter key {key!r}")
        have = got.get(key)
        if want is None:
            if have in (None, [], {}):
                tp += 1
            else:
                fp += 1
                fn += 1
                problems.append(f"{key} set to {have!r} (should be unset)")
        elif isinstance(want, str) and want.upper() == "SET":
            if have in (None, [], {}):
                fn += 1
                problems.append(f"{key} missing")
            else:
                tp += 1
        elif isinstance(want, list):
            want_set = {_norm(v) for v in want}
            have_set = {_norm(v) for v in (have or []) if v is not None}
            tp += len(want_set & have_set)
            missing = want_set - have_set
            extra = have_set - want_set
            fn += len(missing)
            fp += len(extra)
            if missing:
                problems.append(f"{key} missing {sorted(missing)}")
            if extra:
                problems.append(f"{key} extra {sorted(extra)}")
        else:  # a concrete numeric expectation
            if have is None:
                fn += 1
                problems.append(f"{key} missing")
            elif abs(float(have) - float(want)) <= 1e-6:
                tp += 1
            else:
                fp += 1
                fn += 1
                problems.append(f"{key}={have} want {want}")

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    detail = f"P={precision:.2f} R={recall:.2f}"
    if problems:
        detail += " | " + "; ".join(problems)
    return round(f1, 4), detail


def score_candidates(expect: Any, state: Any) -> tuple[float | None, str]:
    if expect is _MISSING or expect is None:
        return None, f"n={len(state.candidates)} (ungraded)"
    produced = len(state.candidates) > 0
    ok = produced is bool(expect)
    return (1.0 if ok else 0.0), f"n={len(state.candidates)} want={'some' if expect else 'none'}"


def score_compliance(state: Any) -> tuple[float | None, str]:
    if not state.drafts:
        return None, "no drafts"
    clean = sum(1 for d in state.drafts if d.compliance.get("ok") is True and d.message.strip())
    return round(clean / len(state.drafts), 4), f"{clean}/{len(state.drafts)} clean"


def score_tools(expect: Any, state: Any) -> tuple[float | None, str]:
    if expect is _MISSING or expect is None:
        return None, ""
    got = [tc.tool for tc in state.tool_calls if tc.ok]
    if got == list(expect):
        return 1.0, f"{len(got)} calls"
    return 0.0, f"got={got or '[]'}"


def score_must_surface(expect: Any, state: Any) -> tuple[float | None, str]:
    if expect is _MISSING or expect is None:
        return None, ""
    want = list(expect)
    ids = {c.counter_id for c in state.candidates}
    hit = [c for c in want if c in ids]
    miss = [c for c in want if c not in ids]
    detail = f"{len(hit)}/{len(want)}"
    if miss:
        detail += f" missing={miss}"
    return round(len(hit) / len(want), 4) if want else None, detail


# --------------------------------------------------------------------------------
# Running one case
# --------------------------------------------------------------------------------
async def run_case(case: dict[str, Any], defaults: dict[str, Any], timeout: float) -> dict[str, Any]:
    from app.agent import AgentState, run_agent

    expect = case["expect"]
    state = AgentState(
        manager_query=case["query"],
        history=[dict(h) for h in case.get("history") or []],
    )

    started = time.perf_counter()
    error: str | None = None
    try:
        async def _drive() -> None:
            async for _ in run_agent(state):
                pass

        await asyncio.wait_for(_drive(), timeout=timeout)
    except Exception as e:  # noqa: BLE001 — a crash is a result, not a reason to stop
        error = f"{e.__class__.__name__}: {e}"
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # `tools` falls back to the standard five-step pipeline unless the case overrides it
    # (`tools: []` for the routes that must not run the pipeline, `null` to skip grading).
    tools_expect = expect.get("tools", _MISSING)
    if tools_expect is _MISSING:
        tools_expect = defaults.get("tools", PIPELINE_TOOLS)

    scores: dict[str, float | None] = {}
    details: dict[str, str] = {}
    for name, fn_args in (
        ("intent", (expect.get("intent", _MISSING), state)),
        ("target_module", (expect.get("target_module", _MISSING), state)),
        ("filters", (expect.get("filters", _MISSING), state)),
        ("language", (expect.get("language", _MISSING), state)),
        ("candidates", (expect.get("candidates", _MISSING), state)),
        ("tools", (tools_expect, state)),
        ("must_surface", (expect.get("must_surface", _MISSING), state)),
    ):
        fn = {
            "intent": score_intent,
            "target_module": score_module,
            "filters": score_filters,
            "language": score_language,
            "candidates": score_candidates,
            "tools": score_tools,
            "must_surface": score_must_surface,
        }[name]
        scores[name], details[name] = fn(*fn_args)  # type: ignore[operator]
    scores["compliance"], details["compliance"] = score_compliance(state)

    graded = [v for v in scores.values() if v is not None]
    return {
        "id": case["id"],
        "group": case.get("group", "ungrouped"),
        "query": case["query"],
        "note": case.get("note", ""),
        "error": error,
        "latency_ms": elapsed_ms,
        "routes": observed_routes(state),
        "scores": scores,
        "details": {k: v for k, v in details.items() if v},
        "case_mean": round(sum(graded) / len(graded), 4) if graded else None,
        "observed": {
            "intent": state.intent,
            "target_module": state.plan.target_module if state.plan else None,
            "language": state.plan.language if state.plan else None,
            "tone": state.plan.tone if state.plan else None,
            "plan_intent": state.plan.intent if state.plan else None,
            "rewritten_query": state.rewritten_query,
            "query_counters_args": actual_filters(state),
            "tools_called": [tc.tool for tc in state.tool_calls if tc.ok],
            "candidate_ids": [c.counter_id for c in state.candidates],
            "candidate_count": len(state.candidates),
            "draft_count": len(state.drafts),
        },
    }


# --------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------
def _cell(v: float | None) -> str:
    if v is None:
        return "  -  "
    if v >= 0.999:
        return " OK  "
    if v <= 0.001:
        return "FAIL "
    return f"{v:5.2f}"


def print_table(results: list[dict[str, Any]]) -> None:
    headers = [label for _, label in DIMENSIONS]
    id_w = max([len(r["id"]) for r in results] + [4])
    head = "  ".join(f"{h:^5}" for h in headers)
    print(f"\n{'case'.ljust(id_w)}  {head}   mean  ms")
    print("-" * (id_w + len(head) + 14))
    for r in results:
        cells = "  ".join(_cell(r["scores"][key]) for key, _ in DIMENSIONS)
        mean = r["case_mean"]
        print(
            f"{r['id'].ljust(id_w)}  {cells}  "
            f"{(f'{mean:.2f}' if mean is not None else '  - '):>5}  {r['latency_ms']:>5}"
        )


def print_failures(results: list[dict[str, Any]]) -> None:
    bad = [r for r in results if r["error"] or any(
        v is not None and v < 0.999 for v in r["scores"].values()
    )]
    if not bad:
        print("\nNo dimension fell short on any case.")
        return
    print(f"\n{len(bad)} case(s) with at least one imperfect dimension:")
    for r in bad:
        print(f"\n  [{r['id']}] {r['query'][:96]}")
        if r["error"]:
            print(f"      ERROR: {r['error']}")
        for key, _ in DIMENSIONS:
            v = r["scores"][key]
            if v is not None and v < 0.999:
                print(f"      {key:<13} {v:.2f}  {r['details'].get(key, '')}")


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, _ in DIMENSIONS:
        vals = [r["scores"][key] for r in results if r["scores"][key] is not None]
        out[key] = {
            "score": round(sum(vals) / len(vals), 4) if vals else None,
            "n": len(vals),
        }
    scored = [v["score"] for v in out.values() if v["score"] is not None]
    out["overall_macro"] = round(sum(scored) / len(scored), 4) if scored else 0.0
    case_means = [r["case_mean"] for r in results if r["case_mean"] is not None]
    out["overall_case_mean"] = round(sum(case_means) / len(case_means), 4) if case_means else 0.0
    return out


def print_aggregate(agg: dict[str, Any], threshold: float) -> None:
    print("\nAggregate per dimension (mean over the cases where the dimension applies)")
    print("-" * 62)
    for key, _ in DIMENSIONS:
        row = agg[key]
        score = row["score"]
        bar = "#" * int(round((score or 0) * 30))
        shown = f"{score:.3f}" if score is not None else "  n/a"
        print(f"  {key:<14} {shown}  (n={row['n']:>2})  {bar}")
    print("-" * 62)
    print(f"  {'OVERALL (macro)':<14} {agg['overall_macro']:.3f}   threshold {threshold:.2f}")
    print(f"  {'per-case mean':<14} {agg['overall_case_mean']:.3f}")


def provider_info() -> dict[str, Any]:
    from app.infrastructure.llm import get_llm_router

    status = get_llm_router().status()
    live = sorted(name for name, up in status.items() if up and name != "mock")
    return {
        "status": status,
        "live_providers": live,
        "mock_only": not live,
        "label": "mock" if not live else "+".join(live),
    }


MOCK_BANNER = (
    "!! MOCK RUN — no API key is configured, so every LLM route was served by\n"
    "!! app/infrastructure/llm/mock.py. The 'planner' under test here is a set of\n"
    "!! regexes that mirror the prompt's own heuristics. These numbers measure the\n"
    "!! harness and the deterministic pipeline; they are NOT evidence about the plan\n"
    "!! quality of a real model. Set ANTHROPIC_API_KEY / GEMINI_API_KEY / GROQ_API_KEY\n"
    "!! and re-run to get a number that means something about the prompt."
)


# --------------------------------------------------------------------------------
async def main_async(args: argparse.Namespace) -> int:
    from app.db.sqlite_engine import bootstrap

    cases_path = Path(args.cases) if args.cases else EVALS_DIR / "cases.yaml"
    if not cases_path.is_absolute():
        cases_path = (Path.cwd() / cases_path).resolve()
    cases, defaults = load_cases(cases_path)

    if args.only:
        needle = args.only.lower()
        cases = [
            c for c in cases
            if needle in c["id"].lower()
            or needle in c["group"].lower()
            or needle in c["query"].lower()
        ]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases matched.", file=sys.stderr)
        return 2

    if args.list:
        for c in cases:
            print(f"{c['id']:<34} [{c['group']}]  {c['query'][:70]}")
        return 0

    bootstrap()
    prov = provider_info()

    print("=" * 78)
    print(f"Counter Copilot — planner evals   ({len(cases)} cases)")
    print(f"cases file : {cases_path}")
    print(f"provider   : {prov['label']}   (live: {prov['live_providers'] or 'none'})")
    print("=" * 78)
    if prov["mock_only"]:
        print(MOCK_BANNER)

    results: list[dict[str, Any]] = []
    for i, case in enumerate(cases, start=1):
        print(f"  [{i}/{len(cases)}] {case['id']} ...", end="", flush=True)
        res = await run_case(case, defaults, timeout=args.timeout)
        results.append(res)
        mean = res["case_mean"]
        print(f" {(f'{mean:.2f}' if mean is not None else 'n/a')}  ({res['latency_ms']} ms)")

    print_table(results)
    print_failures(results)
    agg = aggregate(results)
    print_aggregate(agg, args.threshold)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else EVALS_DIR / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"evals_{prov['label']}_{stamp}.json"
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cases_file": str(cases_path),
        "case_count": len(results),
        "threshold": args.threshold,
        "provider": prov,
        "caveat": (
            "MOCK RUN — served entirely by the deterministic mock LLM. Measures the "
            "pipeline and the mock's regex heuristics, not a real model's plan quality."
            if prov["mock_only"]
            else f"Served by live provider(s): {', '.join(prov['live_providers'])} "
                 "(mock remains the last-resort fallback in LLMRouter)."
        ),
        "aggregate": agg,
        "results": results,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nreport: {report_path}")
    if prov["mock_only"]:
        print("        (labelled provider=mock — do not read it as a model score)")

    passed = agg["overall_macro"] >= args.threshold
    print(
        f"\n{'PASS' if passed else 'FAIL'}: macro {agg['overall_macro']:.3f} "
        f"{'>=' if passed else '<'} threshold {args.threshold:.2f}"
    )
    return 0 if passed else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Grade Counter Copilot's planner against a golden set.")
    p.add_argument("--cases", help="Path to the golden set (default evals/cases.yaml).")
    p.add_argument("--only", help="Run only cases whose id, group or query contains this substring.")
    p.add_argument("--limit", type=int, help="Run at most N cases (after --only).")
    p.add_argument("--threshold", type=float, default=0.85,
                   help="Minimum macro-average across dimensions; below this the run exits 1.")
    p.add_argument("--timeout", type=float, default=180.0, help="Per-case timeout in seconds.")
    p.add_argument("--out", help="Directory for the JSON report (default evals/results).")
    p.add_argument("--list", action="store_true", help="List matching cases and exit.")
    args = p.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
