"""ERP ledger mapping — Billeasy transaction categories → target ERP field surface.

The partner's counter network posts into an external accounting ERP. This tool turns the
Billeasy rail's categories (`ticket_sale`, `retail_bill`, `topup`, `refund`,
`chargeback`, `void_reissue`, `settlement_payout`) into target-ERP ledger/account/tax
postings, deterministically, from a maintained mapping table.

It deliberately does NOT touch a live ERP instance — there is no connector, no secret, no
write path. It generates the *mapping payload a human works from* for onboarding, plus an
honest note on what still needs a human decision (the merchant's tax registration, the
gross-net split of the payout). Out-of-table category names are reported as unmapped
rather than silently guessed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.application.tool_registry import tool

# category -> (ledger / account / tax axis / posting note), per target ERP.
_MAPPINGS: dict[str, dict[str, tuple[str, str, str, str]]] = {
    "tally": {
        "sales": ("Sales Account", "Primary Sales (GST)", "Output GST payable",
                  "Post per ticket_sale/retail_bill collections under the counter's GSTIN."),
        "topup": ("Top-up Income", "Ticket Top-up Income", "GST payable on taxable value",
                  "Top-ups on stored-value cards post as income, not as sales of goods."),
        "settlement_payout": ("Bank Account", "Billeasy settlement clearing", "No tax entry",
                              "Clearing account for the gross payout received from Billeasy; split GST/MDR later."),
        "refund": ("Refund Account", "Sales Returns", "Deduct output GST",
                   "Reverse the original sale entry; net of any chargeback."),
        "chargeback": ("Chargeback Account", "Chargeback losses", "No tax entry",
                       "Loss account, not a sales reversal; carries the chargeback fee."),
        "void_reissue": ("Sales Account", "Primary Sales (GST)", "Output GST payable",
                         "Void and reissue net to zero; log only if reissued at a higher fare."),
        "gst_output": ("GST Payable", "Output GST", "GST ledger",
                       "Monthly GSTR-1 return bucket; reconcile against the GSTIN's portal."),
        "mdr_fee": ("Bank Charges", "MDR / gateway charges", "No tax entry",
                    "Expense account for interchange + MDR deducted from the payout."),
    },
    "zoho_books": {
        "sales": ("Revenue", "Sales - Ticket & Retail", "GST / Sales Tax", "Sales order per collection batch."),
        "topup": ("Revenue", "Top-up Income", "GST / Sales Tax", "Income category for stored-value top-ups."),
        "settlement_payout": ("Bank Account", "Billeasy Settlement Clearing", "None",
                              "Bank deposit of the gross payout; net of fees with the MDR split."),
        "refund": ("Expenses", "Sales Returns", "GST / Sales Tax (reverse)",
                   "Refund debit memo against the original invoice."),
        "chargeback": ("Expenses", "Chargeback Losses", "None", "Loss expense; not a sales reversal."),
        "void_reissue": ("Revenue", "Sales - Ticket & Retail", "GST / Sales Tax",
                         "Void/reissue nets to zero unless the reissue is at a higher fare."),
        "gst_output": ("Liabilities", "Output GST", "GST / Sales Tax", "GSTR-1 return bucket."),
        "mdr_fee": ("Expenses", "MDR & Gateway Charges", "None", "Separate expense line per payout."),
    },
    "sap_b1": {
        "sales": ("Sales - Service", "Sales - Ticket & Retail", "Output Tax",
                  "SD goods/AREA postings per counter attachment."),
        "topup": ("Sales - Service", "Top-up Income", "Output Tax", "Revenue item for stored-value top-ups."),
        "settlement_payout": ("Bank Account", "Billeasy Clearing", "None",
                              "Bank receipt against the gross payout; SAP AR clearing account."),
        "refund": ("Sales - Service", "Sales Returns", "Output Tax (reversal)",
                   "Credit memo linked to the original delivery."),
        "chargeback": ("Expense", "Chargeback Losses", "None", "Chargeback as a loss expense."),
        "void_reissue": ("Sales - Service", "Sales - Ticket & Retail", "Output Tax",
                         "Reversal pair; nets to zero except at higher reissue fare."),
        "gst_output": ("Liabilities", "Output GST", "Output Tax", "Monthly return bucket by GSTIN."),
        "mdr_fee": ("Expense", "MDR & Gateway Charges", "Non-deductible",
                    "Gateway charges as a non-deductible expense line."),
    },
}

_ALLOWED_CATEGORIES = {
    "sales", "topup", "settlement_payout", "refund", "chargeback",
    "void_reissue", "gst_output", "mdr_fee",
}


class GenerateErpMappingIn(BaseModel):
    categories: list[str] = Field(
        description="Billeasy categories to map: sales, topup, settlement_payout, refund, "
                    "chargeback, void_reissue, gst_output, mdr_fee.",
    )
    target: str = Field(description="Target ERP: tally | zoho_books | sap_b1.")


class ErpMappingRow(BaseModel):
    category: str
    ledger: str
    account: str
    tax: str
    posting_note: str


class GenerateErpMappingOut(BaseModel):
    target: str
    mapping: list[ErpMappingRow]
    unmapped: list[str]
    notes: list[str]


@tool(
    name="generate_erp_mapping",
    description=(
        "Generate ledger/account/tax mappings from Billeasy transaction categories to an external "
        "ERP (tally | zoho_books | sap_b1) for onboarding. Deterministic, keyless, no write path — "
        "returns the field mappings plus an onboarding note a partner can work from."
    ),
    input_model=GenerateErpMappingIn,
    output_model=GenerateErpMappingOut,
)
async def generate_erp_mapping(args: GenerateErpMappingIn) -> GenerateErpMappingOut:
    table = _MAPPINGS.get(args.target, {})
    if not table:
        return GenerateErpMappingOut(
            target=args.target,
            mapping=[],
            unmapped=args.categories,
            notes=[f"Unknown target ERP '{args.target}'. Supported: {sorted(_MAPPINGS)}. No mapping generated."],
        )

    rows: list[ErpMappingRow] = []
    unmapped: list[str] = []
    for cat in args.categories:
        if cat not in _ALLOWED_CATEGORIES:
            unmapped.append(cat)
            continue
        entry = table.get(cat)
        if entry is None:
            unmapped.append(cat)
            continue
        ledger, account, tax, note = entry
        rows.append(ErpMappingRow(category=cat, ledger=ledger, account=account, tax=tax, posting_note=note))

    notes = [
        "The settlement payout is the gross figure; the MDR/gateway fee and any chargeback adjust it to net in the ERP.",
        "Check the merchant's GST registration before posting gst_output — an unregistered counter posts no output GST.",
        "No live ERP connection is made; these mappings are the onboarding spec for whoever wires the integration.",
    ]

    return GenerateErpMappingOut(target=args.target, mapping=rows, unmapped=unmapped, notes=notes)
