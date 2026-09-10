# Planner evaluation harness

Grades the **plan** a planner produces for an Area Partner Manager's message — never the
prose. The thing under test is the structured `Plan` (`docs/design.md` / ADR) that the
deterministic tools then execute: the intent route, the target module, the
`query_counters` filter set, the outreach language, the tool sequence, and whether any
pipeline should run at all.

## What gets scored

| Dimension | What counts as right |
| --- | --- |
| `intent` | Routes to the expected intent (`task`, `knowledge`, `faq`, `chitchat`, `out_of_scope`, `follow_up`). |
| `target_module` | The module the plan targets (`MOD-RECON`, `MOD-BILLING`, `MOD-OFFLINE`, …), exactly. |
| `filters` | Set-F1 over the expected `query_counters` keys: a `null` expectation (e.g. "no `min_tpv` on a leakage sweep") is failed if the planner sets it, because a spurious floor silently deletes the very counters being hunted. |
| `language` | The drafting language the plan carries through to message generation. |
| `candidates` | Whether candidates were produced at all — expected `true` for a sweep, `false` for a knowledge/FAQ/chitchat case where running the pipeline answers a question nobody asked. |
| `tools` | The exact tool sequence (defaults to the standard 5-step pipeline; `[]` where the pipeline must not run). |
| `must_surface` | Hero counters that MUST appear in the final ranked candidates — the one place we grade output, not plan, because the hero counter existing in the set is a semantic fact. |
| `compliance` | Every drafted message passes the compliance validator (is grounded in source data). Never off by design. |

## What it deliberately does NOT grade

- **Prose/wording quality.** The same intent expressed badly still scores full marks if
  the structure is right. Style is the synthesizer's job and is judged by a human.
- **Ranking quality beyond the `must_surface` checks.** Queue order is covered by
  `backend/tests/test_ranking.py`.
- **Answer content.** A hallucinated figure inside a draft is caught by the compliance
  validator, not this harness.

## Running it

From `backend/`:

```
PYTHONPATH=. python evals/run_evals.py                 # all cases
PYTHONPATH=. python evals/run_evals.py --only gst       # id/group/query substring
PYTHONPATH=. python evals/run_evals.py --limit 5        # first N (after --only)
PYTHONPATH=. python evals/run_evals.py --list           # show matching cases, no run
```

Flags: `--threshold 0.85` (default) sets the gate — below it the process exits non-zero,
so it can gate CI later. `--out <dir>` relocates the report. `--cases <path>` points at a
different golden set.

## Keyless vs with a key — read the banner

The runner uses whichever provider `LLMRouter` resolves. **With no `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY` or `GROQ_API_KEY` set, every route is served by
`app/infrastructure/llm/mock.py`**, and the run is labelled `provider=mock` in both the
console banner and the report JSON.

**A green mock score is NOT evidence about a real model.** The mock's planner is a set of
regexes that mirror the heuristics written in `planner_system.md`, and the golden set was
written against — and the mock tuned with — those same heuristics. A mock run measures the
harness, the deterministic pipeline, and whether the mock has drifted from the prompt.
Set one free key (Groq or Gemini, both no-card) and re-run; the numbers then mean
something about the prompt itself. The report embeds `provider.live_providers` and a
`caveat` string so a mock result cannot be mistaken for a model result later.

At the time of writing the full 33-case mock run is **33/33, macro 1.000**. Read that as
"the mock now mirrors the prompt's module/filter heuristics for every golden phrasing" —
four of the cases genuinely failed before the mock's `MOD-OFFLINE` / `MOD-BILLING` /
`only-<city>` heuristics were aligned with the prompt, all paraphrase-shaped asks
("keeps going offline during the evening rush", "closing sales without a digital bill",
"Now only Kochi").

## The golden set (`cases.yaml`)

33 cases, 8 groups: leakage sweeps, city/type/tier scoping, GST/receipt gaps, NCMC and
e-ticketing, device downtime, loyalty/QR/analytics growth, non-English drafting (Hindi,
Marathi, Tamil, Gujarati), stateful follow-up refinements, knowledge questions that must
NOT run the pipeline, FAQ, chitchat, out-of-scope, and one adversarial prompt-injection.
Each case records `expect.filters` in a strict grammar — list = exact set, `null` = must
not be set, `"SET"` = must be set to something — that mirrors the tool's argument names
verbatim, so a bad expectation fails loudly in `run_evals.py` rather than silently.

Adding a case: add it to `cases.yaml`, run `--only <id>` to confirm it passes on the
mock, then decide whether the mock or the prompt needs the phrasing — the mock failing
on a canonical phrasing is usually a prompt gap surfaced early.