# Counter Performance Methodology — TPV, Digital Share, Leakage & Settlement Mismatch (Reference Knowledge Base)

> Companion to the counter network database in `backend/data` (SQLite: counters, modules,
> transactions, counter_modules, field_notes). This document defines exactly how Counter
> Copilot computes a counter's monthly TPV, digital share and transaction velocity, how it
> detects revenue leakage, and how it classifies a settlement mismatch.
>
> Everything in this document is a **Billeasy modelling convention** unless it cites an
> external rule. Thresholds are tuned for the demo network and are meant to be reviewed with
> the revenue-assurance team, not quoted to a partner as a regulatory standard.

## 1. The measurement window and the transaction ledger

Every metric is computed from the counter's transaction rows over a stated window. Two
windows are used and must never be mixed in one sentence:

| Window | Definition | Used for |
|---|---|---|
| **Calendar month** | 1st to month-end, the counter's local dates | `monthly_tpv`, reported figures shown to a partner |
| **Rolling 30 days** | Last 30 days to today | Trend features, spike detection, live dashboards |
| **Baseline** | Trailing 90 days **excluding** the last 14 | The "normal" a spike is measured against |
| **Recent** | Last 14 days | The candidate anomaly window |

### Transaction categories and their sign

| Category | Sign | Counts toward TPV? |
|---|---|---|
| `ticket_sale` | positive | **Yes** — collection |
| `retail_bill` | positive | **Yes** — collection |
| `refund` | negative | Yes — reduces net TPV |
| `chargeback` | negative | Yes — reduces net TPV |
| `void_reissue` | positive (paired) | **No** — excluded, it is a correction event |
| `settlement_payout` | positive (money out to the merchant) | **No** — it is the payout leg, not a collection |
| `topup` | positive | **No** — a stored-value load, recognised when spent |
| `other` | either | **No** — excluded unless explicitly reclassified |

Double-counting `settlement_payout` into TPV is the single most common analysis error on this
dataset. Collections and payouts are two sides of the same rupee.

## 2. How monthly TPV, digital share and velocity are computed

### Monthly TPV

```
gross_tpv   = Σ(ticket_sale) + Σ(retail_bill)                    # over the window
net_tpv     = gross_tpv + Σ(refund) + Σ(chargeback)              # both already negative
monthly_tpv = net_tpv                                            # the stored field
```

- `monthly_tpv` on the counter record is **net TPV for the trailing complete calendar month**,
  in ₹.
- Where a counter has fewer than 30 days of history, TPV is **annualised pro-rata from
  observed operating days** and the counter is marked as short-history — never score a
  three-day-old counter against a mature network.
- **`total_collected` vs `total_settled`:** `total_collected` is gross collections at the
  counter; `total_settled` is the sum of `settlement_payout` rows. They are never equal in a
  live month — see §5.

### Digital share and cash share

```
digital_value = Σ(collections where channel ∈ {upi, card, ncmc, wallet, netbanking})
cash_value    = Σ(collections where channel = cash)
digital_share = digital_value / (digital_value + cash_value)
cash_share    = 1 − digital_share
```

- Both are value-weighted (₹), **not** count-weighted. A counter can have 80% of *taps* on UPI
  and still be cash-heavy in rupees, which is precisely the leakage pattern at a ferry jetty.
- `digital_share` is stored on the counter record in the range 0..1.
- A count-weighted variant is computed for diagnostics only and must be labelled as such.

### Transaction velocity

```
avg_daily_txns = count(collection rows in window) / max(operating_days_observed, 1)
txn_velocity   = clamp(avg_daily_txns / 400, 0, 1)      # normalised feature, 0 → 400/day
```

- **Operating days observed** = distinct dates with at least one collection row. Dividing by a
  flat 30 understates a counter that is closed on Mondays or runs a seasonal ferry timetable.
- The `txn_velocity` feature **saturates at 400 transactions/day**. A metro TVM cluster doing
  3,000 taps a day and one doing 900 both score 1.0 — use raw `avg_daily_txns` when comparing
  two high-velocity transit counters.

### Tenure

```
tenure_months = months between onboarded_date and today
tenure_long   = clamp((tenure_months − 3) / (60 − 3), 0, 1)     # normalised 3 → 60 months
```

Counters under 3 months are in ramp-up: their trends are noisy and their leakage flags should
be treated as observations, not accusations.

## 3. The value score — how a counter's network value is computed

Four z-scored features against the live network, combined by the weights in `weights.yaml`:

| Feature | Source | Weight |
|---|---|---|
| `tpv_z` | `monthly_tpv` vs network mean/σ | **0.40** |
| `digital_share_z` | `digital_share` vs network | **0.30** |
| `tenure_z` | months since `onboarded_date` | **0.20** |
| `txn_velocity_z` | `avg_daily_txns` vs network | **0.10** |

Reading it: value rewards **volume that already runs on the digital rail**. A ₹40 lakh counter
at 30% digital share is worth less to the network today than a ₹25 lakh counter at 90% — and
it is simultaneously the bigger leakage opportunity. Value and leakage risk are separate
scores for exactly this reason; never collapse them into one number for a partner.

## 4. Revenue-leakage detection heuristics

Leakage is revenue that **the counter collected but the digital rail never recorded, never
settled, or never billed**. Six heuristics run over every counter.

### L1 — Cash-share spike (fares bypassing the rail)

```
cash_spike_delta = cash_share(last 14 days) − cash_share(baseline 90 days excl. last 14)
cash_share_spike = clamp(cash_spike_delta / 0.40, 0, 1)
```

| Severity | Delta | Reading |
|---|---|---|
| Watch | +0.08 to +0.14 | Seasonal or a device niggle; note it, do not escalate |
| Elevated | +0.15 to +0.29 | Investigate: check device uptime and QR signage first |
| **Severe** | **≥ +0.30** | Escalate to the supervisor with a site visit |

Innocent explanations to rule out **before** the conversation: a dead QR standee, a network
dead-zone, a festival or tourist surge that skews the mix, a broken card reader, and a change
of shift staff who were never trained. Cash-share spike is a **detection signal, not a finding
of fraud**, and the WhatsApp nudge must be worded that way.

**At-risk value** (report this, not "money stolen"):
`at_risk = cash_spike_delta × TPV over the recent window`.

### L2 — Void-and-reissue fraud

The pattern: issue a ticket, void it, keep the cash, then reissue against a fresh fare so the
seat or gate count still balances.

```
void_reissue_rate = count(void_reissue) / count(ticket_sale + retail_bill)
```

| Counter type | Normal band | Investigate above |
|---|---|---|
| Retail | 0.1% – 0.5% | **0.8%** |
| Bus / ferry | 0.4% – 1.2% | **1.8%** |
| Metro / TVM | 0.2% – 0.9% | **1.5%** |

Corroborating signatures that raise confidence from "anomaly" to "case":
1. Void and reissue within a short interval at the **same terminal and same operator ID**.
2. The void is on a **digital** instrument and the reissue is in **cash**.
3. Reissue amounts cluster at round values or at the modal fare.
4. Concentration in one **shift or operator**, not spread across the counter's day.
5. No matching `refund` row and no credit note (see `payments_compliance.md` §4).
6. Spikes in the last 30 minutes of a shift.

### L3 — Settlement mismatch

```
expected_settlement       = collections − platform fees − applicable taxes − refunds/chargebacks
settlement_mismatch_rate  = |expected_settlement − total_settled| / collections
```

| Band | Rate | Action |
|---|---|---|
| Clean | < 0.5% | Timing and rounding; no action |
| Watch | 0.5% – 1.9% | Reconcile at month end |
| **Actionable** | **≥ 2.0%** | Open a reconciliation case; candidate for `MOD-RECON` |
| Critical | ≥ 5.0% | Escalate same day; freeze new module rollout on that counter |

Classify every mismatch into the taxonomy in §5 before writing to anyone. An unclassified
mismatch percentage in a message to a supervisor is the fastest way to lose a partner's trust.

### L4 — Pending settlement backlog

```
pending_settlement_backlog = clamp(pending_settlement / monthly_tpv / 0.25, 0, 1)
```

| Contracted cycle | Expected pending ≈ | Backlog if |
|---|---|---|
| T+1 | ~1–2 days of TPV (3%–7%) | > 10% of monthly TPV |
| T+2 | ~2–3 days of TPV (7%–10%) | > 14% of monthly TPV |
| weekly | ~5–7 days of TPV (17%–24%) | > 30% of monthly TPV |

Backlog is a **churn signal before it is a leakage signal**: an unpaid merchant stops
presenting the digital rail long before they formally terminate.

### L5 — Receipt issuance gap

```
receipt_issuance_gap = count(collections with no digital bill / e-ticket issued)
                       / count(collections)
```

Above **0.25** at a retail counter past ₹5,00,000 monthly TPV, this is the `MOD-BILLING` case
(and, with high transaction counts, the `MOD-WA-RECEIPT` case). A gap is a compliance exposure
for the merchant and a data hole for us: unbilled sales cannot be reconciled or scored.

### L6 — Peak-hour device downtime

```
peak_hour_downtime = clamp(device_offline_minutes_in_peak / 480, 0, 1)
```

Peak windows used by the model: **transit 07:30–11:00 and 17:00–21:00**; **retail 18:00–22:00**.

```
estimated_unrecorded_fares = downtime_minutes × peak_txn_per_minute
estimated_unrecorded_value = estimated_unrecorded_fares × average_ticket
```

At a transit counter, downtime does not stop the passenger — it stops the record. That is why
`MOD-OFFLINE` (offline-first sync) is the answer rather than "fix the network".

## 5. Settlement mismatch taxonomy

Nine classes. Three are benign accounting artefacts, six need action, and two are real
leakage. Always name the class.

| Class | Name | Signature in data | Benign? | Owner | Target resolution |
|---|---|---|---|---|---|
| **M1** | Cut-off timing | Captured after the day's cut-off; settles in the next cycle | Benign | None | Self-clears next cycle |
| **M2** | Fee and take-rate variance | Settled = collections − platform fee − 18% GST on the fee | Benign | Finance | Explain, do not "fix" |
| **M3** | Refund / chargeback offset | A prior-cycle refund nets off this cycle's payout | Benign | Finance | Month-end reconciliation |
| **M4** | Deemed-success capture | Bank/issuer shows success, the rail was never notified; UPI deemed-success class | No | Payments ops | T+2 |
| **M5** | Duplicate capture | Two identical amounts, same instrument, seconds apart — double tap or retry | No | Payments ops | T+2, refund the passenger |
| **M6** | **Offline batch never uploaded** | Device/gate offline minutes, taps missing entirely from the back office | **No — real leakage** | Field / Area Manager | Same day |
| **M7** | Payout return | Beneficiary account or IFSC mismatch, frozen or KYC-expired account; credit reversed | No | Onboarding / KYC | T+1 after correction |
| **M8** | **Cash declared vs deposited** | Counter cash sheet ≠ bank remittance at a transit counter | **No — real leakage** | Operator / authority | Same day, escalate |
| **M9** | Instrument mis-posting | Wallet or NCMC leg settled to the wrong merchant ID or service area | No | Payments ops | T+3 |

Practical rule: **M1, M2 and M3 explain most of a small mismatch.** If a counter is above 2%
and M1–M3 do not account for it, you have a case, not a query.

## 6. Counter tier bands

Tier is assigned from `monthly_tpv` and reviewed monthly. It drives review cadence, module
eligibility and escalation path.

| Tier | Monthly TPV band | Typical avg daily txns | Expected digital share | Review cadence | Typical profile |
|---|---|---|---|---|---|
| **nano** | ₹50,000 – ₹2,00,000 | 10 – 60 | 0.35 – 0.65 | Quarterly, self-serve | Single-till kirana, small feeder-route ticket window |
| **standard** | ₹2,00,000 – ₹8,00,000 | 40 – 200 | 0.50 – 0.80 | Monthly | Neighbourhood provision store, suburban bus counter |
| **flagship** | ₹8,00,000 – ₹25,00,000 | 150 – 700 | 0.70 – 0.92 | Fortnightly, named Area Manager | Supermarket, busy depot window |
| **anchor** | ₹25,00,000 – ₹1,20,00,000 | 500 – 3,500+ | 0.75 – 0.98 | Weekly, joint review with the operator | Jetty counter cluster, metro TVM cluster, large chain outlet |

Notes: bands overlap deliberately at the edges — a counter is not re-tiered on a single
month's swing. Anchor counters are usually **counter clusters under one operator agreement**,
which is why their velocity saturates the `txn_velocity` feature.

## 7. Data dictionary — every field on a counter record

| Field | Type | Meaning |
|---|---|---|
| `id` | str | Counter identifier, e.g. `CTR-0001` |
| `name` | str | Counter name — retail `"{outlet} — {locality}"`, transit `"{jetty/depot/station} — Counter {n}"` |
| `counter_type` | `retail` \| `ferry` \| `bus` \| `metro` | What the counter sells; drives peak windows, void baselines and module fit |
| `city` | str | City the counter operates in |
| `tier` | `nano` \| `standard` \| `flagship` \| `anchor` | TPV band per §6 |
| `operator` | str | Merchant entity or transit agency, e.g. `BEST Undertaking`, `Maharashtra Maritime Board` |
| `monthly_tpv` | float ₹ | Net total payment volume for the trailing complete month (§2) |
| `onboarded_date` | ISO date | Go-live date; source of `tenure_months` |
| `kyc_status` | str | Merchant KYC state — `verified`, `pending`, `expired`. Gates payouts, not scoring |
| `phone` | str | Supervisor / owner phone — the WhatsApp destination. Personal data under DPDP |
| `email` | str \| null | Optional secondary contact |
| `settlement_cycle` | `T+1` \| `T+2` \| `weekly` | Contracted payout cycle; the baseline for backlog aging |
| `pending_settlement` | float ₹ \| null | Amount captured and awaiting payout right now |
| `avg_daily_txns` | float \| null | Collections per operating day (§2) |
| `digital_share` | float 0..1 \| null | Value-weighted share of TPV on digital rails |

**There is no age field on a counter.** Wherever an eligibility band used to be expressed in
years, it is expressed in **daily transactions** (`min_daily_txns` / `max_daily_txns`) on the
module catalogue.

Derived fields that live on the analysis, not on the record: `cash_share`,
`void_reissue_rate`, `settlement_mismatch_rate`, `receipt_issuance_gap`,
`device_offline_minutes`, `peak_hour_downtime`, `ncmc_share`, `refund_ratio`,
`tenure_months`, `leakage_risk`.

**`leakage_risk`** is a composite of L1–L6 above, weighted toward the classes that represent
unrecorded revenue (cash-share spike, void-reissue, offline batch loss) rather than timing
artefacts. It is a **prioritisation score for the Area Manager's day, not an accusation** —
it says "look here first", never "this counter is stealing".

## 8. Worked examples — the five reference counters

Figures below illustrate the method. The live values always come from the counter record;
never quote a worked example to a partner as their number.

### CTR-0001 — Gateway Jetty — Counter 3 (Mumbai, ferry, anchor, Maharashtra Maritime Board)

| Metric | Value |
|---|---|
| Monthly TPV | ₹48,60,000 |
| Avg daily txns | 620 |
| Cash share — baseline (90d) | 22% |
| Cash share — recent (14d) | 61% |
| `cash_share_spike` delta | **+0.39 → Severe** |
| `void_reissue_rate` | 3.1% against a ferry norm of 0.4%–1.2% |
| `settlement_mismatch_rate` | 2.4% — **Actionable**, not explained by M1–M3 |

Working: daily TPV ≈ ₹1,62,000, so the 14-day recent window carries ≈ ₹22,68,000. A +0.39
cash-share shift puts **≈ ₹8.8 lakh of collections off the digital rail** in a fortnight. The
void-reissue rate is 2.6× the ferry norm and clusters in the evening shift with digital voids
followed by cash reissues. Two independent leakage classes plus an actionable mismatch →
**`MOD-RECON` (Settlement & Fare Reconciliation)**. The propensity weights that fire:
`settlement_mismatch_rate` 0.30, `void_reissue_rate` 0.25, `cash_share_spike` 0.20,
`no_recon_module` 0.15, `transit_counter_fit` 0.10. Message the jetty supervisor about a
**joint fare-count reconciliation**, not about suspected theft.

### CTR-0002 — BEST Depot — Wadala Counter 1 (Mumbai, bus, flagship, BEST Undertaking)

| Metric | Value |
|---|---|
| Monthly TPV | ₹14,20,000 |
| Avg daily txns | 310 |
| `device_offline_minutes` in peak | **240 minutes** |
| `peak_hour_downtime` | 240 ÷ 480 = **0.50** |
| `receipt_issuance_gap` | 29% |
| Average ticket | ₹153 |

Working: with ~60% of the day's 310 fares inside the 450-minute peak, throughput is ≈ 0.41
fares/minute. 240 offline minutes ≈ **98 unrecorded fares ≈ ₹15,000 in a single month**, plus
a receipt gap that leaves nearly a third of fares unbilled. The passengers still travelled —
only the record is missing, class **M6**. → **`MOD-OFFLINE` (Offline-First Sync Kit)**, which
queues taps locally and syncs when the link returns.

### CTR-0003 — Sahakari Bhandar — Dadar (Mumbai, retail, flagship, Sahakari Bhandar Retail)

| Metric | Value |
|---|---|
| Monthly TPV | ₹18,00,000 |
| Avg daily txns | 540 |
| Digital share | 0.83 and rising |
| Tenure | 41 months |
| Average basket | ₹111 |
| Live modules | Billing, QR — **no loyalty** |

Working: `tpv_above_10l` = 1, `txn_velocity` = 540/400 → saturated at 1.0, `tenure_long` ≈ 0.67,
`digital_share_trend` positive, `retail_counter_fit` = 1, `no_loyalty_module` = 1. This is a
**healthy** counter — leakage risk is low and the opportunity is repeat-visit value on a high
footfall, low-basket store. → **`MOD-LOYALTY`**. Lead the conversation with the counter's own
numbers (540 baskets a day, 83% digital), not with a discount.

### CTR-0004 — Metro Line-1 Andheri — TVM Cluster (Mumbai, metro, anchor, Mumbai Metro One)

| Metric | Value |
|---|---|
| Monthly TPV | ₹92,00,000 |
| Avg daily txns | ~3,050 taps across the cluster |
| `ncmc_share` | **8%** |
| Average fare | ₹100 |
| Live modules | QR, Analytics — **no e-ticketing** |

Working: velocity saturates the normalised feature at 1.0, so compare on raw taps. Only 8% of
~91,500 monthly taps are on NCMC; the rest queue for paper or QR tickets at the window. Moving
NCMC share from 8% to a realistic 35% shifts **≈ 24,700 taps a month to tap-and-go**, cutting
queue time, cash handling and the window's reconciliation load. → **`MOD-ETICKET` (Transit
e-Ticketing, QR + NCMC)**. Note the model weights `ncmc_share` **negatively** for this module:
low NCMC share is what creates the upside, and a counter already at 60% NCMC would not surface.

### CTR-0005 — Shree Provision Stores — Pune (Pune, retail, standard, Shree Provision Stores)

| Metric | Value |
|---|---|
| Monthly TPV | ₹5,40,000 |
| Avg daily txns | 95 |
| `gst_threshold_crossed` | **1** (TPV ≥ ₹5,00,000) |
| `receipt_issuance_gap` | **46%** |
| Average ticket | ₹189 |

Working: ~2,850 collections a month, of which **1,311 carry no digital bill ≈ ₹2,47,700 of
sales unbilled**. Annualised turnover is ≈ ₹65 lakh — comfortably past the GST **registration**
thresholds, so compliant billing is a live obligation for this merchant (it is nowhere near
the ₹5 crore **e-invoicing** threshold — do not conflate the two, see
`payments_compliance.md` §1). Weights that fire: `receipt_issuance_gap` 0.30,
`gst_threshold_crossed` 0.30, `retail_counter_fit` 0.20, `no_existing_module_bonus` 0.20. →
**`MOD-BILLING` (Digital Billing & GST e-Invoice)**.

## 9. How the Area Manager consumes this

1. Every counter record links its live modules, TPV trend, digital share, settlement position
   and recent field notes in one **Counter 360** view.
2. The agent surfaces the **single most actionable signal** — "cash share 22% → 61% in three
   weeks, void-reissue at 3.1%" — plus the recommended module, so the Area Manager can act in
   one glance.
3. Prioritisation blends **network value** (§3) with **leakage risk** (§4), with urgency
   weighted toward unrecorded-revenue classes and toward counters whose payout is aging past
   their contracted cycle.
4. Every figure in an outreach message must be traceable to the counter's own rows. The
   numeric compliance validator blocks anything else — an unsupported number is a blocking
   failure, not a wording preference.
