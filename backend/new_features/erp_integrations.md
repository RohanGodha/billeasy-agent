# ERP & Accounting Integration Guide

How a Billeasy partner's counter network posts into an external ERP. This guide covers the
integration surface — categories, ledgers, GST/tax axes, settlement clearing — and how to use
Counter Copilot's `generate_erp_mapping` tool to produce the mapping spec for a target ERP
(Tally, Zoho Books, SAP Business One). Nothing here connects to a live ERP: the agent has no
integration secret and makes no write call; the mapping is the onboarding spec for whoever wires
the ERP connector.

## The Billeasy transaction categories (what must land in the ledger)
- `ticket_sale` — a transit ticket sold (ferry/bus/metro). B2C usually, B2B (corporate
  contract corridors) needs an e-invoice.
- `retail_bill` — a retail POS sale with a bill; GST documents flow from here.
- `topup` — stored-value / prepaid top-up; income, not goods sale.
- `refund` — money returned to the customer (negative amount).
- `chargeback` — bank reversed a captured amount after a dispute (negative amount, with the
  chargeback fee as a separate expense).
- `void_reissue` — a ticket voided and re-issued; net zero unless reissued at a higher fare.
- `settlement_payout` — the gross collection Billeasy paid out (the merchant's bank receipt).

## Golden posting rules
1. **Gross-in, split-out**: post the settlement payout gross; split MDR/gateway fees and any
   chargeback into their own expense lines — never net them silently.
2. **GST axis per GSTIN**: every posted sale/top-up/refund carries the counter's GSTIN; an
   unregistered counter posts no output GST. Do not mix GSTINs in one return bucket.
3. **Clearing account discipline**: the settlement clears through a dedicated Billeasy clearing
   account; the ERP bank balance then only reflects *paid* payouts, which is what cash
   management needs.
4. **Void/reissue is a reversal pair**: it never books revenue twice. The only volume it
   affects is the audit trail (reconciliation and loss-checks), not the P&L.

## Per-ERP mapping (generated, not guessed)
Run `generate_erp_mapping` with the categories you post and the target ERP and it returns the
ledger/account/tax/posting-note per category. The table is maintained in the tool code; the
generated output is the spec. Supported targets today: `tally`, `zoho_books`, `sap_b1`.

## Onboarding checklist for a new partner ERP
- Confirm the partner's GST registration status per counter before enabling `gst_output`.
- Decide gross-vs-net posting for `settlement_payout` (gross recommended; net hides the MDR).
- Choose the clearing account name the partner's bookkeeper recognises (one per partner is
  fine; one per target ERP must not collide).
- Test-reconcile one month's payout batch against the ERP bank statement before switching the
  whole network.

## What Counter Copilot will NOT do
- It will not open a session to the ERP, post a journal, or read the ERP's balances.
- It will not invent a provider-specific field the mapping table does not carry — unmapped
  categories are reported as `unmapped`, never silently dropped.
- It will not treat an external accounting discrepancy as settlement fraud; ERP-side
  differences are ledger-period issues, not payout losses, until the reconciliation says
  otherwise.