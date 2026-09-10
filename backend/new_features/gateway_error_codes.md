# Gateway & Settlement Error Codes

Reference for what a Counter Copilot partner actually sees when a ticket sale fails between
the counter terminal, a payment gateway and Billeasy's settlement rail — and which failure to
escalate as **counter-side**, **gateway-side**, or **bank-side**.

## How a digital ticket sale flows
1. Customer's UPI/card app → Billeasy rail → payment gateway → issuing bank. Approval returns
   the same way.
2. The rail **captures** the approved amount immediately. `capture` = money is taken from the
   customer.
3. Settlement is a separate step: Billeasy collects everything captured in a day, applies MDR/
   gateway fees, and pays the merchant through a **payout batch** (usually T+1 per the counter's
   settlement cycle).
This is why "customer paid but I didn't get it yet" is most often a *settlement timing* issue,
not a chargeback or a gateway failure.

## Failure classes and what they mean
- **Gateway timeout (capture timeout)** — the acquiring gateway took too long to answer. The
  customer may or may not have been charged. The counter must **reconcile the same ticket before
  recharging**: recharging on a timeout without checking is how double-charges happen.
- **Gateway decline** — the issuing bank refused. No money moves. Common reasons: insufficient
  balance, a fraud rule, daily-limit cap, or a `generic_decline` (do not retry immediately —
  retry burns another decline and can trip fraud rules).
- **Bank decline vs gateway decline** — the gateway literally returns the bank's response code.
  Treat "insufficient funds / blocked card / limit" as bank-side and permanent for that attempt;
  treat "try again later" and timeouts as gateway-side and retryable.
- **Capture vs payout mismatch** — captured money is not yet in the payout batch. Check: is the
  pending settlement batch present? If yes → settlement timing, expected. If a whole day is
  simply missing → settlement railing failure, escalate to the Billeasy ops desk, not the
  counter operator.
- **Chargeback** — the bank reversed a captured amount after the customer disputed it. This is
  *not* a settlement error; it posts as a negative amount on the rail and lands in the refund/
  chargeback ledger.

## Error-code cheat sheet (UPI/card gateways commonly seen in India)
- `ZP:/NA` UPI "attempt limit hit".
- `ZP:/CU` UPI "customer not found on this VPA".
- `generic_decline` (STP) — declined, do not retry same method immediately.
- `insufficient_funds` — bank-side, permanent for this attempt.
- `processing_error` / `timeout` / `gateway_timeout` — RETRYABLE after one reconciliation.
- `fraud_suspected` — bank flagged; stop retrying, verify identity.
- `card_blocked` / `expired_card` — bank-side permanent for that instrument.
These codes are illustrative of what Indian gateways map to; the counter ledger does not store
the raw code, so Counter Copilot can name the *class* of failure, not the exact provider code.

## Settlement norms
- Standard: **T+1** — daily batch pays next working day. Weekly counters get one payout a week.
- **Nodal vs escrow**: UPI payments hold in a nodal account per RBI; the payout release depends
  on the peg that passes Billeasy's applicability condition. If a payout is delayed, check the
  peg delay first — the money is safe, it is waiting on the schedule, not lost.
- A **pending_settlement** balance that keeps climbing on the same counter for days is the
  strongest single "money not moving" flag for a partner — worth a reconciliation triage run.

## What the partner should do, by class
- Counter-side (void/reissue, unissued bills, offline terminal) → operate on the counter, use
  field-ops checks.
- Gateway-side (timeouts, retryable declines) → reconcile the ticket, retry, and if repeat,
  talk to the gateway support stack Billeasy uses.
- Bank-side (insufficient funds, card blocked) → inform the customer; do not keep retrying.
- Settlement railing (whole-day shortfall, missing batch) → raise to the Billeasy ops desk with
  the counter id and batch date. Never ask the counter operator to "resend" money they already
  moved.