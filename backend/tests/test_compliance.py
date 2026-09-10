"""The numeric-grounding validator — the guardrail between the model and a merchant.

This exists because the assertion in the smoke and e2e tests (`compliance.ok is True`)
is **vacuous**: the deterministic mock writes drafts containing no digits, so the
validator has nothing to ground and passes trivially. Eleven green assertions were
telling us nothing about the control they claimed to cover.

These tests make it actually fire: a draft that invents a figure must be caught and
redacted, and a draft quoting real figures must survive intact.
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.scoring.compliance import compliance_check

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    # Source context mirroring what generate_whatsapp_message actually passes.
    context = {
        "counter": {
            "name": "Gateway Jetty — Counter 3",
            "monthly_tpv": 2500000,
            "pending_settlement": 452700,
            "avg_daily_txns": 410,
        },
        "module": {"name": "Settlement & Fare Reconciliation", "take_rate": 0.5},
        "aggregates": {"cash_share": 0.61, "void_reissue_count": 7},
    }

    # --- 1. An invented figure must be caught and redacted --------------------
    bad = (
        "Hello Gateway Jetty team, our records show ₹9,87,654 stuck in settlement and "
        "a 42% cash share this month. Shall we fix it?"
    )
    r = compliance_check(bad, context)
    check("ungrounded draft is flagged", r["ok"] is False, str(r["ungrounded"]))
    check(
        "the invented settlement figure is detected",
        "987654" in r["ungrounded"],
        str(r["ungrounded"]),
    )
    check(
        "the invented figure is redacted out of the message",
        "987654" not in r["redacted_draft"].replace(",", ""),
        r["redacted_draft"],
    )
    check(
        "redaction leaves the prose readable",
        "Gateway Jetty" in r["redacted_draft"] and "—" in r["redacted_draft"],
        r["redacted_draft"],
    )

    # --- 2. A draft quoting real figures must pass untouched ------------------
    good = (
        "Hello Gateway Jetty — Counter 3 team, ₹4,52,700 is currently pending "
        "settlement and we counted 7 void-and-reissue events. Can we talk this week?"
    )
    r = compliance_check(good, context)
    check("grounded draft passes", r["ok"] is True, str(r["ungrounded"]))
    check("grounded draft is not modified", r["redacted_draft"] == good)

    # --- 3. Rounding tolerance ------------------------------------------------
    # "₹4.5 lakh" for 452700 is a legitimate human rounding, not a hallucination.
    rounded = "About ₹4.5 lakh is pending settlement at your counter."
    r = compliance_check(rounded, context)
    print(f"        rounding case -> ok={r['ok']} ungrounded={r['ungrounded']}")

    # --- 4. A number that is close but wrong must NOT slide through -----------
    wrong = "Hello team, ₹8,52,700 is pending settlement at your counter."
    r = compliance_check(wrong, context)
    check(
        "a plausible-but-wrong figure is still caught",
        r["ok"] is False,
        str(r["ungrounded"]),
    )

    # --- 5. No numbers at all is trivially compliant --------------------------
    # Documented explicitly so nobody mistakes this for meaningful coverage again.
    r = compliance_check("Can we schedule a call about your counter this week?", context)
    check("a draft with no figures passes trivially", r["ok"] is True)

    if failures:
        print(f"\nCompliance test FAILED: {failures}")
        return 1
    print("\nCompliance tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
