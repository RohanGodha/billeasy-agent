"""Invoice-layout validator — deterministic structural checks on pasted invoice text.

Companion to the numeric revenue-assurance pipeline: the agent can flag *which* counters
crossed the e-invoicing band, but a partner pasting a sample bill still wants to know
whether it is layout-compliant. This tool runs the same kind of bounded, keyless checks
as the compliance scorer — no LLM, no provider call — over the pasted text:

  - GSTIN present and format-valid (always, for a tax invoice),
  - HSN/SAC code present (6 or 8 digits) for goods-heavy bills,
  - a monetary total present (₹/Rs/INR figure),
  - IRN present when the seller claims e-invoicing (advisory: only flagged, never fatal),
  - GSTIN on the seller line when the bill self-labels "tax invoice".

It does NOT claim to certify layout beyond what is structurally checkable in text, and
its help text points at the regulatory corpus for the band/date rules.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.application.tool_registry import tool

_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[A-Z0-9]\b")
_HSN_RE = re.compile(r"\bHSN[: ]?[:\s]?(\d{4}|\d{6}|\d{8})\b", re.IGNORECASE)
_SAC_RE = re.compile(r"\bSAC[: ]?[:\s]?(\d{4}|\d{6}|\d{8})\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR)\s?\d[\d,]*\.?\d*", re.IGNORECASE)
_IRN_RE = re.compile(r"\bIRN[: ]{0,2}[A-Za-z0-9-]{20,}\b", re.IGNORECASE)
_TAX_INVOICE_LABEL = re.compile(r"\btax invoice\b", re.IGNORECASE)


class LayoutIssue(BaseModel):
    severity: str  # "error" | "warning"
    code: str
    found: str | None = None
    message: str


class ValidateInvoiceLayoutIn(BaseModel):
    invoice_text: str = Field(min_length=10, description="The invoice content, pasted as-is.")
    require_tax_fields: bool = Field(
        default=True,
        description="When the bill self-labels a tax invoice, require GSTIN/HSN/amount.",
    )


class ValidateInvoiceLayoutOut(BaseModel):
    ok: bool
    checked_fields: dict[str, bool]
    issues: list[LayoutIssue]


@tool(
    name="validate_invoice_layout",
    description=(
        "Structural GST invoice-layout check on pasted invoice text: validates GSTIN format, "
        "HSN/SAC presence, that a rupee total is stated, and flags a missing IRN when the bill "
        "self-labels as e-invoiced. Deterministic and keyless. Returns ok + issues with error/"
        "warning severity. Does not certify layout beyond what is textually checkable."
    ),
    input_model=ValidateInvoiceLayoutIn,
    output_model=ValidateInvoiceLayoutOut,
)
async def validate_invoice_layout(args: ValidateInvoiceLayoutIn) -> ValidateInvoiceLayoutOut:
    text = args.invoice_text.strip()
    self_claims_tax = bool(_TAX_INVOICE_LABEL.search(text))

    has_gstin = bool(_GSTIN_RE.search(text))
    has_hsn = bool(_HSN_RE.search(text))
    has_sac = bool(_SAC_RE.search(text))
    has_amount = bool(_AMOUNT_RE.search(text))
    has_irn = bool(_IRN_RE.search(text))

    issues: list[LayoutIssue] = []
    require = args.require_tax_fields and self_claims_tax

    if require and not has_gstin:
        issues.append(LayoutIssue(
            severity="error", code="missing_gstin",
            found="no GSTIN",
            message="A self-labelled tax invoice must carry the seller's 15-character GSTIN.",
        ))
    if require and (not has_hsn and not has_sac):
        issues.append(LayoutIssue(
            severity="error", code="missing_hsn_sac",
            found="no HSN/SAC",
            message="Tax invoices must state an HSN or SAC code (4, 6 or 8 digits per the "
                    "turnover band) for at least the main line.",
        ))
    if not has_amount:
        issues.append(LayoutIssue(
            severity="error", code="missing_total",
            found="no ₹/Rs/INR figure",
            message="The bill must state a monetary total; the compliance check can't quantify an amountless bill.",
        ))
    if self_claims_tax and not has_gstin:
        issues.append(LayoutIssue(
            severity="error", code="self_claim_unsupported",
            found="labelled 'tax invoice' without GSTIN",
            message="The document labels itself a tax invoice but no valid GSTIN appears in the text.",
        ))
    if self_claims_tax and has_irn is False and has_gstin:
        issues.append(LayoutIssue(
            severity="warning", code="irn_absent",
            found="no IRN",
            message="E-invoiced bills carry an IRN. Absence may be fine below the e-invoicing band — see "
                    "the regulatory schedule for the current threshold and effective dates.",
        ))

    checked = {
        "gstin": has_gstin,
        "hsn_or_sac": has_hsn or has_sac,
        "amount": has_amount,
        "irn": has_irn,
        "self_claims_tax": self_claims_tax,
    }
    return ValidateInvoiceLayoutOut(
        ok=not any(i.severity == "error" for i in issues),
        checked_fields=checked,
        issues=issues,
    )
