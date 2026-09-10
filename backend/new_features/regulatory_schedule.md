# Billeasy Regulatory & Compliance Schedule

Effective-dated view of the payments / GST obligations a Billeasy partner network must
satisfy. `effective_from` dates answer the partner's "does this apply to me now / what
changed" deterministically — Counter Copilot retrieves the row and the answer states the
date, so a rule that has not started is reported as **rolling out**, never as already due.

## GST & e-invoicing
- **GST e-invoicing for B2B supplies** — registered suppliers above the notified turnover
  threshold must issue e-invoices (IRN) through the Invoice Registration Portal.
  `effective_from`: threshold notified each FY; current event threshold ₹5,00,00,000
  (₹50L on events) aggregate turnover. Reporting: GSTR-1, monthly for regular taxpayers,
  quarterly under QRMP.
- **HSN/SAC declaration** — tax invoices must state an HSN or SAC code: 2-digit for
  turnover up to ₹5 crore, 4/6/8-digit above, 8-digit on B2B. `effective_from`: every
  invoice dated after the taxpayer's threshold crossing.
- **Credit / debit notes** — a supplementary document to the original invoice; requires the
  original GSTIN and the note's own serial; used to adjust taxable value or tax in the period
  the adjustment is contracted/witnessed.
- **TDS under GST?** — no. GST does not use TDS; tax is output-side only for the seller. (TDS
  applies to income tax, not GST.)

## Payments (RBI)
- **Payment Aggregator (PA) authorisation** — Billeasy operates under PA rules: merchant
  money sits in a **nodal account** held with a scheduled bank; payout happens against the
  daily settlement peg (see `gateway_error_codes.md`).
- **UPI**: inter-operable through NPCI; settlement is a daily netting; UPI has no MDR on
  person-to-merchant (P2M) UPI up to the day's cap under the zero-MDR regime — a payment
  aggregator cannot charge the merchant an MDR line on exempt UPI.
- **NCMC / One Nation One Card**: stored-value transit card; AFC gate writes value-off;
  settlement to the transit authority per the card scheme's T+1 clearing.
- **Prepaid / stored value** — top-up collections are the merchant's, but load must never
  exceed the RBI cap per instrument (₹2,00,000 for full-KYC prepaid instruments).

## Customer & data
- **DPDP Act 2023** — every counter that handles a customer's personal data (phone, PAN,
  ticket history) must give the customer a notice, get consent where consent is the ground,
  and honour erasure requests within the grace window. Billeasy is the data fiduciary; the
  counter is a controller in its own records. Penalties scale with the class of breach.
- **KYC / e-KYC** — counters onboard under Billeasy's KYC ("know your customer") flow: a
  registered entity supplies PAN + cancelled cheque/bank proof; individuals supply Aadhaar
  e-KYC / V-CIP. Refres stay valid until the customer's profile changes (change of entity,
  name, bank account).

## Where the companion checkpoints are
- Layout of a tax invoice → run `validate_invoice_layout` on a sample bill.
- Whether a *counter* crossed a band → run the compliance sweep (`query_counters` with the
  billing module gating), which flags outlets for the e-invoice / HSN duty.
- What changed recently → watch this schedule: each row carries its effective_from and the
  summary lines above are the current-rule snapshot.