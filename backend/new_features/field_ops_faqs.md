# Field Operations FAQs — Area Partner Manager Playbook (Referenced in Real Time)

> Authoritative FAQ document for Counter Copilot. The assistant retrieves answers from this
> file in real time and grounds its reply, rather than relying on the model's memory or only
> the structured database.
>
> Audience: **Area Partner Managers** running 200–500 live counters — retail outlets and
> government mass-transit ticketing counters (ferry jetties, bus depots, metro stations).
> Regulatory detail is in `payments_compliance.md`; metric definitions are in
> `counter_performance_methodology.md`. Items marked **[product convention]** are Billeasy
> operating practice, not law.

## A. Onboarding a counter

### 1. How does a new counter go live?
Capture the outlet or operator details and the supervisor's contact, run merchant KYC and
bank-account verification, sign the merchant or agency agreement with the commercial terms
(settlement cycle and module take rates), provision the device or QR, train the counter
staff on one live transaction, then go live and watch the first settlement land. A clean
retail onboarding takes 2–5 working days; a transit counter takes longer because the
agreement sits with the authority, not the window.

### 2. What does a retail merchant need to submit?
PAN of the entity and of the signatory, an Officially Valid Document for identity and
address (Aadhaar, Passport, Voter ID, Driving Licence), proof of business — GSTIN, Shop &
Establishment licence or Udyam registration — a cancelled cheque or bank statement in the
entity's name, and photographs of the storefront and the till point. Companies and
partnerships add the Certificate of Incorporation or partnership deed, a board resolution
or authority letter, and beneficial-ownership details.

### 3. How is a government transit counter different?
The **merchant is the transit authority**, not the ticket window. Onboarding runs off an
**agency agreement** with the authority (for example a maritime board, a bus undertaking or
a metro operator); fare revenue settles to the authority's **designated revenue account**;
and individual counters are provisioned as locations under that agreement rather than as
separately KYC'd merchants. Counter staff are agency employees — they are operators, not
account holders. Never negotiate commercial terms at the window.

### 4. What is captured about the counter itself?
Counter name, type (retail / ferry / bus / metro), city, operator, onboarding date,
contracted settlement cycle, supervisor phone and email, and the device or QR provisioned.
Everything else — TPV, digital share, velocity, tier, pending settlement — is **computed
from transactions**, never keyed in by hand.

### 5. How soon can a new counter be scored or targeted?
**[product convention]** Give it **at least 3 months**. Under 3 months a counter is in
ramp-up: trends are noisy, the baseline for spike detection does not exist yet, and most
module eligibility rules carry a minimum-tenure condition. Flag early anomalies as
observations, not findings.

### 6. What usually goes wrong in the first month?
Bank details that fail penny-drop verification, a GSTIN that does not match the entity
name, staff who were trained on the device but not on issuing the bill, a QR standee that
nobody put on the counter, and a supervisor's number that was never opted in — so no
settlement alerts reach anyone.

## B. The Area Partner Manager's role

### 7. What does an Area Partner Manager actually own?
A geography of counters and their health: that they transact, that the digital rail
captures what they collect, that they settle on time, that they issue compliant bills, and
that the operator or owner stays a willing partner. The Area Manager is the escalation path
between the counter floor and Billeasy's payments, onboarding and finance desks.

### 8. How does the Area Manager prioritise a day?
By a blend of **network value** and **leakage risk**, with urgency weighted toward
unrecorded-revenue signals (cash-share spikes, void-and-reissue patterns, offline batches
that never uploaded) and toward counters whose payout is aging past its contracted cycle.
Highest-value, highest-risk, most-urgent first.

### 9. What can the Area Manager decide alone?
Site visits, retraining, device swaps and replacements, reprinting signage, raising a
reconciliation case, and recommending a module. **Not** alone: changing a settlement cycle,
waiving or discounting a take rate, releasing a held payout, overriding KYC, or accepting a
merchant's version of a mismatch without reconciliation.

### 10. Is a leakage flag an accusation?
 No. It says **"look here first"**. A cash-share spike has innocent explanations far more
 often than dishonest ones — a dead QR standee, a network dead-zone, a broken card reader,
 a festival crowd, a new shift that was never trained. Verify on site before the
 conversation changes tone, and word every message as a joint check, never as a charge.

### 11. What does the Area Manager do after a module goes live?
 Confirm the module is actually being used (not just provisioned), watch the metric it was
 sold to fix — mismatch rate, receipt gap, downtime, NCMC share — for two full cycles, and
 close the loop with the supervisor using their own numbers. A module that goes live and
 changes nothing is a churn risk, not a win.

## C. Merchant KYC

### 12. Why does a payments platform run KYC at all?
 Because a Payment Aggregator handles other people's money. RBI's PA framework requires a
 board-approved merchant onboarding policy and **KYC checks on every merchant** in line
 with the Master Direction on KYC, plus AML and sanctions screening. No KYC, no settlement.

### 13. What counts as a valid identity document?
 The Officially Valid Documents: **Aadhaar, PAN, Passport, Voter ID and Driving Licence**,
 with a recent photograph. PAN is required for the entity and must be linked to Aadhaar
 where applicable.

### 14. What is CKYC, and does it help?
 The **Central KYC Registry**. Once KYC is done with one regulated entity, a **14-digit
 CKYC identifier** lets the same records be reused across regulated entities instead of
 being collected again. It shortens onboarding but does not remove entity-level checks such
 as GSTIN and bank verification.

### 15. What is video KYC (V-CIP)?
 RBI-permitted remote customer identification over a live, geo-tagged video call with a
 trained official, used for fully digital onboarding when a field visit is impractical.

### 16. Who is a beneficial owner, and why is it asked?
 The natural person who ultimately owns or controls the entity. Under the PMLA rules the
 identification threshold is **10% ownership or control for companies and partnerships**
 and **15% for unincorporated associations**; trusts are identified through settlor,
 trustee and beneficiaries. It exists to stop a shell entity from taking settlements.

### 17. How often is KYC refreshed, and what happens if it lapses?
 Risk-based periodic updation: **high risk every 2 years, medium risk every 8 years, low
 risk every 10 years**. If it lapses, **payouts stop** even though collections continue —
 which shows up as `kyc_status` moving off `verified` and `pending_settlement` climbing
 with no matching payout. That is an onboarding problem masquerading as a settlement
 complaint.

## D. Settlement and payouts

### 18. What does T+1 actually mean to a merchant?
 Money captured on day T is credited on the next **settlement day** — not the next
 24 hours. Sundays, second and fourth Saturdays and bank holidays push it out, and a
 capture after the day's cut-off belongs to the next T. A Friday-evening ferry rush usually
 lands Monday or Tuesday.

### 19. Where does the money sit before it reaches the merchant?
 In an **escrow account with a scheduled commercial bank**. It is not Billeasy's working
 capital, cannot be pledged, and may only be debited for merchant payouts, refunds and
 chargebacks, and the platform's own commission — which must move out within T+1. For a
 transit counter the funds settle to the authority's designated revenue account.

### 20. Why is the payout smaller than the day's collections?
 Three ordinary reasons, in this order: the **platform fee** for the modules live on that
 counter, **18% GST on that fee**, and **refunds or chargebacks netted off**. Cut-off
 timing explains most of the rest. If those do not account for the gap, it is a genuine
 mismatch — classify it before saying anything (see `counter_performance_methodology.md`
 §5). Tax treatment questions go to Billeasy's finance desk; never improvise a tax answer
 for a merchant.

### 21. Does the merchant pay MDR on UPI?
 **No. MDR is zero on UPI (P2M) and on RuPay debit cards** by law. The platform fee is a
 separate charge for the software — the bill or e-ticket, the reconciliation, the payout —
 and is not affected by the zero-MDR rule. Say this precisely: merchants conflate the two
 constantly, and getting it wrong destroys credibility.

### 22. A supervisor says "yesterday's money hasn't come." What do I check, in order?
 (1) Is it a settlement day, and was capture before cut-off? (2) Is `kyc_status` still
 verified? (3) Did a payout attempt **fail and return** — account or IFSC mismatch, name
 mismatch, frozen or dormant account? (4) Are there refunds or chargebacks netting it off?
 (5) Are there **offline batches that never uploaded**, so the fares were never reported?
 (6) Only then raise a reconciliation case. Give the supervisor a real timeline, never a
 guess.

### 23. When is a pending balance actually a problem?
 **[product convention]** Roughly: above **10% of monthly TPV on a T+1 counter**, above
 **14% on T+2**, and above **30% on a weekly cycle**. A backlog is a churn signal before it
 is a leakage signal — an unpaid partner stops presenting the digital rail long before they
 formally leave.

## E. Disputes and chargebacks

### 24. What is a chargeback, and how is it different from a refund?
 A **refund** is the merchant returning money voluntarily. A **chargeback** is the card
 issuer reversing a settled transaction on the cardholder's dispute, against the acquirer
 and then the merchant. UPI disputes run through NPCI's dispute-resolution system rather
 than the card networks. In the ledger both are **negative** rows and both reduce net TPV.

### 25. What are the timelines?
 RBI's **harmonisation of turnaround times** circular sets auto-reversal deadlines for
 failed transactions with **₹100 per day compensation** for delay beyond them — for
 example, a UPI debit with no beneficiary credit reverses by T+1, and a card transaction
 debited but not confirmed at the point of sale reverses within the prescribed window. Card
 chargebacks additionally follow the network's dispute cycle — commonly around **120 days**
 from the transaction for an issuer to raise it and roughly **30 days** for the acquirer to
 represent. Confirm the current network rules before quoting a date to a merchant.

### 26. How does a counter win a representment?
 With evidence at the moment of sale: the digital bill or e-ticket with its reference
 number, EMV terminal data or the signed charge slip, the tap/authorisation log, proof of
 delivery or of travel, and — for transit — the AFC gate record. **[product convention]**
 Counters with `MOD-BILLING` or `MOD-ETICKET` live win representments far more often,
 simply because the evidence exists. That is a legitimate and honest reason to recommend
 the module.

### 27. A passenger was charged but the gate did not open. Is that a chargeback?
 Usually not. Gate-level fare disputes — a failed tap-out charged at maximum fare, a double
 tap, a deducted fare with no travel — are corrected by the operator's **AFC back office**
 as a fare adjustment, not by a card dispute. Duplicate captures at the counter (class M5)
 are refunded by us. Route it correctly the first time; a wrongly-raised chargeback costs
 the merchant a fee.

## F. Partner relationship tips

### 28. When is the right moment to recommend a module?
 When the counter's own data has just made the case: a mismatch that stayed above 2% for
 two cycles, a cash-share spike that survived a device check, a receipt gap at a counter
 past ₹5,00,000 monthly TPV, repeated peak-hour downtime, or a high-velocity transit counter
 still on paper tickets. Also good: right after a clean settlement run, when trust is high.

### 29. How do you raise a leakage conversation without accusing anyone?
 Lead with the observation and the joint action, not the inference. *"Counter 3's cash
 share moved from 22% to 61% over three weeks — can we do a fare-count reconciliation
 together on Thursday and check the QR standee and the reader?"* Bring the number, bring a
 proposed time, and let the site visit establish the cause.

### 30. How do you build trust that survives a bad month?
 Quote only figures the counter's own data supports — never round up, never estimate into a
 message. Explain the platform fee and zero MDR honestly before you are asked. Give real
 settlement timelines instead of optimistic ones. Message the supervisor's opted-in number
 only, keep to utility notices for settlement and compliance matters, honour an opt-out
 immediately, keep messages short and signed off in your own first name, and close every
 loop you open. These are partners running a shop or a public service, not leads.
