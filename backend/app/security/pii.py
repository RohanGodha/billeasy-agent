"""PII masking guard (DPDP-focused).

Billeasy counters and their merchants sit under India's DPDP Act — README §12 documents
the consent/notice posture. This module redacts personally identifiable information from
any free text before it is:

  - sent to an LLM (prompt assembly in the router, planner, synthesizer, generator),
  - handed to the knowledge base for retrieval,
  - persisted into the `messages` thread, session titles, or `agent_traces`.

It is applied at two chokepoints so no caller can bypass it:

  1. the chat boundary (`app.api.chat`) — before the query is stored, titled, or built
     into an `AgentState`, and
  2. the agent entry gate (`app.agent.graph.run_agent`) — so direct `AgentState`
     callers (tests, scripts) get the same protection.

Masking is idempotent: placeholders such as `[GSTIN]` do not re-trigger any pattern, so
re-running over already-masked text is a no-op and safe.

Patterns cover the canonical DPDP identifiers India's financial rail carries:
GSTIN (a 15-char business/PAN identifier), PAN, Aadhaar, mobile number, and email.
Open-secret business contact fields (counter name, city, operator) are deliberately NOT
masked — redacting them would destroy every downstream answer and DPDP's protection of
personally-identifiable data does not require blanking a registered business identity.
"""
from __future__ import annotations

import re

_MASK = {
    "gstin": "[GSTIN]",
    "pan": "[PAN]",
    "aadhaar": "[AADHAAR]",
    "phone": "[PHONE]",
    "email": "[EMAIL]",
}

# GSTIN: two state digits + PAN (10) + entity code + 'Z' + checksum. Must run before PAN
# so the embedded PAN core is swallowed whole by the wider pattern.
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[A-Z0-9]\b")
# PAN: a standalone 5 letters + 4 digits + 1 letter surrounded by word boundaries.
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
# Indian mobile written WITH the 91 country code: 12 digits starting "91" + a 6-9 digit.
# Must precede the bare-12-digit aadhaar so it is labelled a phone, not an aadhaar.
_PHONE_CC_RE = re.compile(r"\b91[6-9]\d{9}\b")
# Aadhaar: spaced 4-4-4 form first (unambiguous), then a bare 12-digit run.
_AADHAAR_SPACED_RE = re.compile(r"\b\d{4} \d{4} \d{4}\b")
_AADHAAR_PLAIN_RE = re.compile(r"\b\d{12}\b")
# Indian mobile: 10 digits starting 6-9, optionally +91/-/0 prefixed and grouped as
# 5-5 blocks. The (?!\d) guard stops a partial match inside any longer digit run that
# survived the rules above.
_PHONE_RE = re.compile(r"(?:[+]91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
# Email: the plain RFC-5322-ish shape, host TLD at least two letters.
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")

_RULES: list[tuple[re.Pattern[str], str]] = [
    (_GSTIN_RE, _MASK["gstin"]),
    (_PAN_RE, _MASK["pan"]),
    (_PHONE_CC_RE, _MASK["phone"]),
    (_AADHAAR_SPACED_RE, _MASK["aadhaar"]),
    (_AADHAAR_PLAIN_RE, _MASK["aadhaar"]),
    (_PHONE_RE, _MASK["phone"]),
    (_EMAIL_RE, _MASK["email"]),
]


def mask_pii(text: str | None) -> str:
    """Redact PII identifier patterns, returning the masked text.

    Order matters for prefix overlap only, which the standalone-PAN rule avoids via
    word boundaries; each rule replaces its matches independently.
    """
    if not text:
        return text or ""
    out = text
    for pattern, placeholder in _RULES:
        out = pattern.sub(placeholder, out)
    return out
