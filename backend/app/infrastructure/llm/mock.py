"""Deterministic mock LLM.

Activates when no API keys are configured. Lets the entire agent pipeline run
end-to-end offline so reviewers can exercise the system without spending money.

It returns:
  - For planner JSON requests: a sensible canned plan covering the canonical
    "ferry and bus counters leaking digital ticket revenue" ask.
  - For critic JSON requests: a pass verdict.
  - For synthesizer requests: a templated ranked answer built from whatever
    rendered candidate context appears in the user message.
  - For message generation: a templated WhatsApp nudge using the provided
    counter/module context.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from .base import LLMClient, LLMMessage, LLMResponse


class MockLLM(LLMClient):
    name = "mock"
    supports_json = True

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        start = time.perf_counter()
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        system = "\n".join(m.content for m in messages if m.role == "system").lower()
        text, data = self._dispatch(system, last_user, json_mode)
        elapsed = int((time.perf_counter() - start) * 1000)
        return LLMResponse(
            text=text,
            json_data=data if json_mode else None,
            model="mock-1",
            provider=self.name,
            latency_ms=elapsed,
            tokens_in=len(last_user) // 4,
            tokens_out=len(text) // 4,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Deterministic 'hash-bag' embeddings — good enough for cosine ordering in dev."""
        dim = 256
        vectors: list[list[float]] = []
        for t in texts:
            vec = [0.0] * dim
            for word in re.findall(r"[a-zA-Z]+", t.lower()):
                idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % dim
                vec[idx] += 1.0
            # L2 norm
            mag = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / mag for v in vec])
        return vectors

    async def health(self) -> bool:
        return True

    # -------------------------------------------------------------------
    # Routing inside the mock — match on **node tags**, not free-text
    # The real prompts include `[node:planner]` / `[node:critic]` etc., which
    # cannot collide with words like "CRITICAL" inside body copy.
    # -------------------------------------------------------------------
    _NODE_PATTERNS = {
        "intent":      re.compile(r"route a message from a billeasy"),
        "follow_up":   re.compile(r"refining their previous request|rewrite their new message"),
        "faq":         re.compile(r"knowledge base"),
        "chitchat":    re.compile(r"conversational message"),
        "guardrail":   re.compile(r"outside the scope|politely decline"),
        "planner":     re.compile(r"\[node:planner\]|decompose the area manager|executable plan"),
        "critic":      re.compile(r"\[node:critic\]|the \*\*critic\*\* node|critic.{0,20}node"),
        "synthesizer": re.compile(r"\[node:synthesizer\]|the \*\*synthesizer\*\*|synthesi[sz]e"),
        "whatsapp":    re.compile(r"writing a whatsapp message"),
    }

    def _dispatch(self, system: str, user: str, json_mode: bool) -> tuple[str, dict[str, Any]]:
        u_low = user.lower()
        s = system  # already lowercased by caller
        # Most specific cues first.
        if self._NODE_PATTERNS["follow_up"].search(s):
            return self._follow_up(user)
        if self._NODE_PATTERNS["intent"].search(s):
            return self._intent(u_low)
        if self._NODE_PATTERNS["faq"].search(s):
            return self._faq()
        if self._NODE_PATTERNS["chitchat"].search(s):
            return self._chitchat(user)
        if self._NODE_PATTERNS["guardrail"].search(s):
            return self._guardrail()
        if self._NODE_PATTERNS["whatsapp"].search(s):
            return self._whatsapp(user)
        if self._NODE_PATTERNS["critic"].search(s):
            return self._critic()
        if self._NODE_PATTERNS["synthesizer"].search(s):
            return self._synthesize(user)
        if self._NODE_PATTERNS["planner"].search(s):
            return self._plan(u_low)
        if json_mode:
            data = {"ok": True, "note": "mock-llm response"}
            return json.dumps(data), data
        return ("This is a deterministic mock response from Counter Copilot. Configure "
                "GEMINI_API_KEY or GROQ_API_KEY for real LLM output."), {}

    def _intent(self, user_lower: str) -> tuple[str, dict[str, Any]]:
        # Mirror the node heuristic so offline classification is sensible.
        new_msg = user_lower.split("new message:")[-1]
        data = {"intent": "task", "reason": "mock"}
        if re.match(r"\s*(hi|hey|hello|thanks|thank you|ok|bye)", new_msg):
            data["intent"] = "chitchat"
        elif re.search(r"poem|code|weather|joke|movie|recipe", new_msg):
            data["intent"] = "out_of_scope"
        elif re.match(
            r"\s*(help|back|go back|cancel|stop|reset|restart|start over|start again|"
            r"clear (the )?(session|chat|conversation|history))\s*[.!?]*\s*$",
            new_msg,
        ):
            data["intent"] = "command"
        elif re.search(
            r"gst|e-?invoice|irn|hsn|rbi|nodal|escrow|mdr|ncmc|afc gate|dpdp|"
            r"payment aggregator|t\+1|t\+2|settlement (cycle|norm|history|rule)|"
            r"chargeback|merchant kyc|take rate|reconciliation (rule|process)|"
            r"which modules (are|is) (live|running)|settlement history|payout history",
            new_msg,
        ):
            data["intent"] = "knowledge"
        elif re.search(r"\b(you|your)\b", new_msg) and re.search(r"what|which|how|can|who|do you", new_msg):
            data["intent"] = "faq"
        return json.dumps(data), data

    def _follow_up(self, user: str) -> tuple[str, dict[str, Any]]:
        prev = re.search(r"Previous:\s*'([^']*)'", user)
        new = re.search(r"New:\s*'([^']*)'", user)
        base = prev.group(1) if prev else ""
        ref = new.group(1) if new else ""
        rewritten = f"{base} ({ref})".strip() if base else ref
        data = {"rewritten": rewritten}
        return json.dumps(data), data

    def _faq(self) -> tuple[str, dict[str, Any]]:
        text = (
            "I can search your counter network, score each counter's value and leakage risk, "
            "recommend the right Billeasy module, and draft compliance-checked WhatsApp nudges "
            "for the supervisor or outlet owner. Try: \"Find ferry and bus counters in Mumbai "
            "leaking digital ticket revenue this month and draft WhatsApp nudges for the depot "
            "supervisors.\""
        )
        return text, {"summary": text}

    def _chitchat(self, user: str) -> tuple[str, dict[str, Any]]:
        name = "Rohan"
        m = re.search(r"(?:area )?manager name:\s*([A-Za-z]+)", user, re.IGNORECASE)
        if m:
            name = m.group(1).capitalize()
        said = ""
        sm = re.search(r"(?:area )?manager just said:\s*(.+)", user, re.IGNORECASE | re.DOTALL)
        if sm:
            said = sm.group(1).lower()
        if re.search(r"\b(bye|goodbye|see (you|ya)|cya|take care|good ?night|later)\b", said):
            text = f"See you, {name}. I'll be here when you need the next sweep of your counters."
        elif re.search(r"\b(thanks?|thank you|thx|cheers)\b", said):
            text = f"Anytime, {name}. Tell me a city, a counter type or a module whenever you're ready."
        elif re.search(r"\b(how are you|how'?s it going|what'?s up|sup)\b", said):
            text = (
                f"Ready to go, {name}. Point me at a city or counter type and I'll find the counters "
                "that are leaking revenue."
            )
        else:
            text = (
                f"Hi {name}! I'm Counter Copilot — every counter, accounted for. Tell me which counters "
                "to look at and I'll flag revenue leakage and settlement gaps, recommend the right "
                "Billeasy module, and draft WhatsApp nudges for the supervisors."
            )
        return text, {"summary": text}

    def _guardrail(self) -> tuple[str, dict[str, Any]]:
        text = (
            "That's outside what I can help with. I'm your counter revenue-assurance copilot — I find "
            "counters, flag revenue leakage and settlement mismatches, recommend Billeasy modules, and "
            "draft supervisor outreach."
        )
        return text, {"summary": text}

    # -------------------------------------------------------------------
    # Sourced from the seeded network rather than hardcoded. A hand-maintained list
    # drifted from the data and silently broke city filtering: "Kochi" wasn't in it, so
    # "my Kochi ferry counters" planned with no city filter at all and answered with
    # counters from three other cities. Deriving it means the mock cannot fall behind
    # the seeder again.
    @staticmethod
    def _city_vocab() -> tuple[str, ...]:
        try:
            from app.db.seeders.faker_seed import INDIAN_CITIES

            return tuple(c.lower() for c in INDIAN_CITIES)
        except Exception:  # noqa: BLE001 - keep the mock usable if the seeder moves
            return (
                "mumbai", "pune", "bangalore", "delhi", "hyderabad", "chennai",
                "kolkata", "ahmedabad", "jaipur", "lucknow", "indore",
                "chandigarh", "kochi", "surat",
            )

    _TIERS = ("nano", "standard", "flagship", "anchor")

    def _plan(self, user_lower: str) -> tuple[str, dict[str, Any]]:
        # Heuristic module selection mirroring the planner prompt's heuristics.
        module_hint = "MOD-RECON"
        if re.search(
            r"device (offline|down)|peak[- ]hour|machine hang|downtime|network drop|offline sync|"
            r"going offline|goes offline|evening rush|rush[- ]hour",
            user_lower,
        ):
            module_hint = "MOD-OFFLINE"
        elif re.search(
            r"gst|e-?invoice|irn|bill(s)? not issued|receipt gap|receipt issuance|invoice|"
            r"without (a )?(digital )?bill|\bno (digital )?bill\b|aren'?t issuing|not issuing|"
            r"aren'?t giving (bills|receipts|receipts)",
            user_lower,
        ):
            module_hint = "MOD-BILLING"
        elif re.search(r"ncmc|e-?ticket|transit ticket|qr ticket|afc gate|paper ticket", user_lower):
            module_hint = "MOD-ETICKET"
        elif re.search(r"loyalty|rewards|repeat customers|footfall", user_lower):
            module_hint = "MOD-LOYALTY"
        elif re.search(r"whatsapp receipt|digital bill to|engagement", user_lower):
            module_hint = "MOD-WA-RECEIPT"
        elif re.search(r"dashboard|analytics|reporting|insights|counter performance", user_lower):
            module_hint = "MOD-ANALYTICS"
        elif re.search(r"cash[- ]heavy|accept upi|dynamic qr|no digital collection", user_lower):
            module_hint = "MOD-QR"

        counter_types: list[str] = []
        if re.search(r"ferry|jetty|jetties", user_lower):
            counter_types.append("ferry")
        if re.search(r"\bbus\b|depot", user_lower):
            counter_types.append("bus")
        if re.search(r"metro|station|tvm", user_lower):
            counter_types.append("metro")
        if re.search(r"retail|outlet|shop|store|kirana|provision", user_lower):
            counter_types.append("retail")

        city_filter: list[str] = []
        for city in self._city_vocab():
            if city in user_lower:
                city_filter.append(city.title())

        # "Now only Kochi" replaces the earlier city scope, it does not add to it. The
        # rewritten follow-up text still carries the original cities ("… Mumbai …
        # (Now only Kochi)"), so when the message names a single city after "only",
        # that city is the scope and the others drop out.
        only_match = re.search(r"\bonly\s+([a-z]+)\b", user_lower)
        only_city = only_match.group(1) if only_match else ""
        if only_city in self._city_vocab() and city_filter and city_filter != [only_city.title()]:
            city_filter = [only_city.title()]

        # Tier ("anchor counters with…") and settlement-backlog asks map to real filters.
        tiers = [t for t in self._TIERS if re.search(rf"\b{t}\b", user_lower)]
        wants_backlog = bool(
            re.search(r"backlog|pending settlement|unpaid|payout (delay|pending)", user_lower)
        )

        language = "English"
        for lang in ["hindi", "marathi", "tamil", "telugu", "kannada", "gujarati", "bengali", "punjabi"]:
            if lang in user_lower:
                language = lang.capitalize()
                break

        # Leakage / compliance sweeps stay broad so struggling counters are not
        # filtered out before scoring; growth asks can gate on TPV.
        is_leakage_sweep = module_hint in {"MOD-RECON", "MOD-OFFLINE", "MOD-BILLING"}
        plan = {
            "intent": "detect_counter_revenue_leakage_and_nudge_supervisors",
            "target_module": module_hint,
            "city_filter": city_filter,
            "tone": (
                "warm" if "warm" in user_lower
                else ("formal" if "formal" in user_lower else "professional")
            ),
            "language": language,
            "steps": [
                {
                    "step": 1, "tool": "query_counters",
                    "args": {
                        "cities": city_filter or None,
                        "counter_types": counter_types or None,
                        "tiers": tiers or None,
                        # A leaking counter is not necessarily a high-TPV counter,
                        # so we do not gate the sweep on TPV — propensity surfaces it.
                        "min_tpv": (None if is_leakage_sweep else 500000),
                        # Only when the manager actually asked about money waiting to
                        # be paid out; otherwise it would filter healthy counters out.
                        "min_pending_settlement": (50000 if wants_backlog else None),
                        "limit": (150 if is_leakage_sweep else 80),
                        "exclude_modules": [module_hint],
                    },
                    "expected": "Shortlist of candidate counters.",
                },
                {
                    "step": 2, "tool": "compute_counter_value",
                    "args": {"counter_ids": "$step1.ids"},
                    "expected": "Network-value score per counter with feature contributions.",
                },
                {
                    "step": 3, "tool": "predict_module_propensity",
                    # Score the *whole* queried set, not just the value-top slice, so a
                    # small counter with a severe leakage signal is not filtered out early.
                    "args": {"counter_ids": "$step1.ids", "module_id": module_hint},
                    "expected": "Module propensity and leakage drivers per counter.",
                },
                {
                    "step": 4, "tool": "recommend_modules",
                    "args": {
                        "counter_ids": "$step3.top_k",
                        "candidate_module_ids": [module_hint],
                        "top_k": 1,
                    },
                    "expected": "Eligibility-checked Billeasy module recommendation per counter.",
                },
                {
                    "step": 5, "tool": "search_field_notes",
                    "args": {"query": user_lower[:80], "k": 5},
                    "expected": "Field-note snippets to ground the drafts.",
                },
            ],
        }
        return json.dumps(plan), plan

    def _critic(self) -> tuple[str, dict[str, Any]]:
        data = {"verdict": "pass", "replan": False, "notes": "Subtask satisfied; proceed."}
        return json.dumps(data), data

    _CAND_LINE = re.compile(r"^\s*-\s*(?P<name>.+?)\s*\((?P<meta>[^)]*)\)\s*—\s*(?P<rest>.+)$")

    def _synthesize(self, user: str) -> tuple[str, dict[str, Any]]:
        """Rank the rendered candidate context into a believable Counter Copilot answer."""
        block = user.split("Candidates:", 1)[-1]
        lines = [ln for ln in block.splitlines() if ln.strip().startswith("-")]
        ranked: list[str] = []
        for i, ln in enumerate(lines[:5], start=1):
            m = self._CAND_LINE.match(ln)
            if m:
                signal = m.group("rest").split("top signal:")[-1].strip().rstrip(".")
                ranked.append(f"{i}. {m.group('name')} ({m.group('meta')}) — {signal}.")
            else:
                ranked.append(f"{i}. {ln.strip().lstrip('- ').strip()}")

        if not ranked:
            text = (
                "No counter in this sweep showed a leakage or settlement signal strong enough to "
                "flag. Widen the city or counter-type filter and run it again."
            )
            return text, {"summary": text}

        text = (
            f"{len(ranked)} counter(s) in your area are showing revenue-leakage or settlement "
            "signals, ranked by combined network value and module fit:\n\n"
            + "\n".join(ranked)
            + "\n\nEach row carries its own explainable score breakdown — cash-share movement, "
            "void-and-reissue rate, settlement mismatch and receipt-issuance gap — plus a "
            "compliance-checked WhatsApp draft for the counter supervisor. Review the right pane "
            "to approve, edit or send. All amounts in ₹."
        )
        return text, {"summary": text}

    def _whatsapp(self, user: str) -> tuple[str, dict[str, Any]]:
        """Build a data-grounded draft from the structured payload (counter, module, signals)."""
        counter = "there"
        module = "this module"
        manager = "Rohan"
        counter_match = re.search(r"Counter:\s*\n\s*name:\s*([^\n]+)", user, re.IGNORECASE)
        if counter_match:
            counter = counter_match.group(1).strip()
        module_match = re.search(r"module:\s*\n\s*name:\s*([^\n]+)", user, re.IGNORECASE)
        if module_match:
            module = module_match.group(1).strip()
        manager_match = re.search(r"Area Partner Manager:\s*([A-Za-z]+)", user)
        if manager_match:
            manager = manager_match.group(1).strip()

        signals = user.lower()
        if "cash_share_spike" in signals or "cash share" in signals:
            observation = "we're seeing more of your collections coming in as cash lately"
        elif "settlement_mismatch" in signals:
            observation = "our records show captured collections and settled payouts drifting apart"
        elif "void_reissue" in signals:
            observation = "we've noticed a run of tickets being voided and reissued at your counter"
        elif "receipt_issuance_gap" in signals or "gst" in signals:
            observation = "a share of sales at your counter are going out without a digital bill"
        elif "peak_hour_downtime" in signals or "device_offline" in signals:
            observation = "your device has been dropping offline during the peak rush"
        elif "pending_settlement" in signals:
            observation = "there's a payout still sitting in your pending settlement queue"
        else:
            observation = "looking at the last few weeks of activity at your counter"

        warm = "warm" in signals
        opener = f"Hi {counter} team," if warm else f"Hello {counter} team,"
        text = (
            f"{opener} {observation}. Our {module} would close that gap and keep every "
            f"sale on the digital rail. Can I call you this week to walk through it? — {manager}"
        )
        return text, {"message": text}
