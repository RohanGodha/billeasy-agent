"""Hand-crafted hero counters used in the demo scenarios.

These counters are designed so the scoring engine surfaces them naturally — not by
hardcoding — for their respective Billeasy modules. Their transaction rows, channel
mix and field-visit notes carry the exact signals the scorer is tuned for, and the
arithmetic below genuinely produces the headline numbers quoted in the persona note.

Conventions used by the seeded transaction rows (the scorers rely on these):

* ``category`` in {ticket_sale, retail_bill, void_reissue} are **collections**.
  ``settlement_payout`` is money paid out to the operator (positive).
  ``refund`` / ``chargeback`` are negative.
* ``cash_share``      = Rs on ``channel='cash'`` / Rs of collections.
* ``digital_share``   = 1 - cash_share.
* ``receipt_issuance_gap`` = collection rows with ``instrument IS NULL``
  (no GST bill / e-ticket issued) as a share of collection rows.
* ``settlement_mismatch_rate`` = (collections - settlement_payout) / collections.
* ``ncmc_share``      = ``channel='ncmc'`` share of ``ticket_sale`` rows.
* The ``digital_share`` stored on the counter row is the **current** (most recent
  window) share, which is what the Area Manager is alerted on — for counters that
  are drifting it deliberately differs from the all-time average over 90 days.
* ``peak_hour_downtime`` is visible as a hole in the transaction clock times during
  the evening peak window (17:00-21:00) on the outage day.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal


@dataclass
class HeroTxn:
    days_ago: int
    amount: float
    category: str
    channel: str = "upi"
    instrument: str | None = None
    hour: int = 12
    minute: int = 0


@dataclass
class HeroFieldNote:
    days_ago: int
    channel: str
    summary: str


@dataclass
class HeroCounter:
    id: str
    name: str
    counter_type: Literal["retail", "ferry", "bus", "metro"]
    city: str
    tier: Literal["nano", "standard", "flagship", "anchor"]
    operator: str
    monthly_tpv: float
    phone: str
    email: str
    onboarded_years_ago: int
    device_type: str
    pending_settlement: float
    avg_daily_txns: float
    digital_share: float
    # Peak-window minutes the terminal was unreachable, as the device estate reports it.
    device_offline_minutes: float = 0.0
    settlement_cycle: str = "T+1"
    # DPDP outreach consent for the demo: the leakage showcase counter is opted out so
    # the agent visibly refuses its otherwise-top pitch; the rest are opted in.
    consent_ok: bool = True
    txns: list[HeroTxn] = field(default_factory=list)
    field_notes: list[HeroFieldNote] = field(default_factory=list)
    existing_modules: list[str] = field(default_factory=list)
    expected_module: str = ""
    persona_note: str = ""


# ---------------------------------------------------------------------------
# CTR-0001 — Gateway Jetty, Counter 3 (ferry, anchor)
# Cash share 22% -> 61% in three weeks + void/reissue spike -> MOD-RECON
#   recent  (d1-d20):  cash 15,45,500 / collections 25,20,500 = 61.3%
#   baseline(d25-d90): cash 11,02,200 / collections 50,02,200 = 22.0%
#   collections 75,22,700 over ~90d  ->  monthly TPV ~ Rs 25,00,000
#   void_reissue 7 / 35 rows = 20% (6 of them inside the 3-week cash spike)
#   settlement mismatch (75,22,700 - 70,70,000) / 75,22,700 = 6.0%
#   receipt gap only 2 / 30 collection rows = 6.7% — the problem here is
#   reconciliation, not billing
# ---------------------------------------------------------------------------
_CTR1_TXNS: list[HeroTxn] = [
    # --- recent window: cash floods back in ---
    HeroTxn(2, 237500, "ticket_sale", "cash", None, 8, 40),
    HeroTxn(5, 262500, "ticket_sale", "cash", None, 9, 15),
    HeroTxn(8, 220000, "ticket_sale", "cash", "Cash Drawer", 18, 5),
    HeroTxn(11, 280000, "ticket_sale", "cash", "Cash Drawer", 8, 25),
    HeroTxn(14, 255000, "ticket_sale", "cash", "Cash Drawer", 19, 10),
    HeroTxn(18, 270000, "ticket_sale", "cash", "Cash Drawer", 9, 5),
    HeroTxn(3, 175000, "ticket_sale", "upi", "PhonePe UPI", 8, 50),
    HeroTxn(6, 162500, "ticket_sale", "upi", "Google Pay UPI", 18, 20),
    HeroTxn(9, 150000, "ticket_sale", "ncmc", "RuPay NCMC", 9, 35),
    HeroTxn(12, 187500, "ticket_sale", "upi", "PhonePe UPI", 19, 25),
    HeroTxn(16, 137500, "ticket_sale", "card", "RuPay Debit", 10, 15),
    HeroTxn(19, 162500, "ticket_sale", "upi", "Paytm UPI", 18, 45),
    # void-then-reissue burst on the same shifts as the cash spike
    HeroTxn(4, 3500, "void_reissue", "cash", "Reissued Ticket", 18, 35),
    HeroTxn(7, 3100, "void_reissue", "cash", "Reissued Ticket", 19, 5),
    HeroTxn(10, 4000, "void_reissue", "cash", "Reissued Ticket", 18, 55),
    HeroTxn(13, 2900, "void_reissue", "cash", "Reissued Ticket", 19, 40),
    HeroTxn(15, 3400, "void_reissue", "cash", "Reissued Ticket", 18, 15),
    HeroTxn(17, 3600, "void_reissue", "cash", "Reissued Ticket", 19, 20),
    # --- baseline window: mostly digital ---
    HeroTxn(30, 187500, "ticket_sale", "cash", "Cash Drawer", 9, 10),
    HeroTxn(45, 200000, "ticket_sale", "cash", "Cash Drawer", 18, 30),
    HeroTxn(60, 237500, "ticket_sale", "cash", "Cash Drawer", 9, 45),
    HeroTxn(75, 225000, "ticket_sale", "cash", "Cash Drawer", 19, 15),
    HeroTxn(88, 250000, "ticket_sale", "cash", "Cash Drawer", 8, 55),
    HeroTxn(27, 650000, "ticket_sale", "upi", "PhonePe UPI", 9, 20),
    HeroTxn(38, 625000, "ticket_sale", "upi", "Google Pay UPI", 18, 40),
    HeroTxn(50, 675000, "ticket_sale", "ncmc", "RuPay NCMC", 8, 30),
    HeroTxn(58, 600000, "ticket_sale", "upi", "Paytm UPI", 19, 0),
    HeroTxn(68, 700000, "ticket_sale", "card", "Visa Debit", 9, 50),
    HeroTxn(80, 650000, "ticket_sale", "upi", "PhonePe UPI", 18, 10),
    HeroTxn(40, 2200, "void_reissue", "cash", "Reissued Ticket", 18, 25),
    # --- settlements out to the maritime board revenue account ---
    HeroTxn(21, 2360000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 30),
    HeroTxn(51, 2355000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 30),
    HeroTxn(81, 2355000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 30),
    # --- refunds on cancelled sailings ---
    HeroTxn(9, -45000, "refund", "upi", "PhonePe UPI", 16, 20),
    HeroTxn(43, -55000, "refund", "upi", "Google Pay UPI", 16, 40),
]

# ---------------------------------------------------------------------------
# CTR-0002 — BEST Depot, Wadala Counter 1 (bus, flagship)
# Handheld dead for the full 17:00-21:00 evening peak on d3 = 240 minutes,
# plus a receipt-issuance gap -> MOD-OFFLINE
# Each row is one shift batch of pass/ticket sales.
#   collections 43,50,000 over ~90d -> monthly TPV Rs 14,50,000
#   cash 9,14,400 = 21.0%  (no spike — this counter's problem is downtime)
#   receipt gap 13 / 33 collection rows = 39.4% (35.9% by value)
#   settlement mismatch (43,50,000 - 42,30,000) / 43,50,000 = 2.8%  (low on purpose)
# ---------------------------------------------------------------------------
_CTR2_TXNS: list[HeroTxn] = [
    # d1 — normal day, both peaks served
    HeroTxn(1, 157200, "ticket_sale", "upi", "PhonePe UPI", 8, 20),
    HeroTxn(1, 115200, "ticket_sale", "cash", None, 9, 40),
    HeroTxn(1, 170400, "ticket_sale", "upi", "Paytm UPI", 18, 10),
    HeroTxn(1, 93600, "ticket_sale", "ncmc", "RuPay NCMC", 19, 30),
    # d2 — normal
    HeroTxn(2, 139200, "ticket_sale", "upi", "Google Pay UPI", 8, 30),
    HeroTxn(2, 124800, "ticket_sale", "cash", None, 18, 20),
    HeroTxn(2, 158400, "ticket_sale", "upi", None, 19, 40),
    # d3 — OUTAGE: nothing recorded between 10:45 and 21:20 -> the whole
    #      17:00-21:00 evening peak (240 minutes) is missing
    HeroTxn(3, 144000, "ticket_sale", "upi", "PhonePe UPI", 8, 15),
    HeroTxn(3, 108000, "ticket_sale", "cash", None, 9, 30),
    HeroTxn(3, 122400, "ticket_sale", "upi", None, 10, 45),
    HeroTxn(3, 57600, "ticket_sale", "upi", None, 21, 20),
    # d5 — normal
    HeroTxn(5, 146400, "ticket_sale", "upi", "PhonePe UPI", 8, 25),
    HeroTxn(5, 81600, "ticket_sale", "ncmc", "RuPay NCMC", 9, 50),
    HeroTxn(5, 165600, "ticket_sale", "upi", "Paytm UPI", 18, 5),
    HeroTxn(5, 112800, "ticket_sale", "cash", None, 19, 45),
    # d7 — normal
    HeroTxn(7, 136800, "ticket_sale", "upi", "Google Pay UPI", 8, 40),
    HeroTxn(7, 105600, "ticket_sale", "cash", None, 10, 10),
    HeroTxn(7, 163200, "ticket_sale", "upi", "PhonePe UPI", 18, 50),
    # d9 — normal
    HeroTxn(9, 141600, "ticket_sale", "upi", None, 8, 35),
    HeroTxn(9, 163200, "ticket_sale", "upi", "Paytm UPI", 18, 15),
    HeroTxn(9, 110400, "ticket_sale", "cash", None, 19, 50),
    # d12 — normal
    HeroTxn(12, 151200, "ticket_sale", "upi", "PhonePe UPI", 8, 45),
    HeroTxn(12, 86400, "ticket_sale", "ncmc", "RuPay NCMC", 9, 55),
    HeroTxn(12, 168000, "ticket_sale", "upi", None, 18, 25),
    # d14 — normal
    HeroTxn(14, 144000, "ticket_sale", "upi", "Google Pay UPI", 8, 20),
    HeroTxn(14, 120000, "ticket_sale", "cash", None, 18, 30),
    HeroTxn(14, 153600, "ticket_sale", "upi", "PhonePe UPI", 19, 20),
    # --- older reference shifts ---
    HeroTxn(33, 139200, "ticket_sale", "upi", "PhonePe UPI", 8, 30),
    HeroTxn(33, 160800, "ticket_sale", "upi", "Paytm UPI", 18, 20),
    HeroTxn(45, 117600, "ticket_sale", "cash", None, 9, 10),
    HeroTxn(45, 156000, "ticket_sale", "upi", "Google Pay UPI", 19, 0),
    HeroTxn(62, 144000, "ticket_sale", "upi", "PhonePe UPI", 8, 50),
    HeroTxn(62, 91200, "ticket_sale", "ncmc", "RuPay NCMC", 18, 40),
    # --- settlements ---
    HeroTxn(16, 1490000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 15),
    HeroTxn(46, 1440000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 15),
    HeroTxn(76, 1300000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 15),
    HeroTxn(8, -29000, "refund", "upi", "PhonePe UPI", 15, 30),
]

# ---------------------------------------------------------------------------
# CTR-0003 — Sahakari Bhandar, Dadar (retail, flagship)
# Rs 18L TPV, high velocity, digital share climbing 68% -> 91%, no loyalty module
#   recent  (d1-d18):  digital 16,38,000 / 18,00,000 = 91.0%
#   baseline(d28-d82): digital 24,48,000 / 36,00,000 = 68.0%
#   collections 54,00,000 over 90d -> monthly TPV Rs 18,00,000
# ---------------------------------------------------------------------------
_CTR3_TXNS: list[HeroTxn] = [
    # --- recent: almost fully digital ---
    HeroTxn(2, 315000, "retail_bill", "upi", "PhonePe UPI", 11, 20),
    HeroTxn(5, 277500, "retail_bill", "card", "RuPay Debit", 19, 10),
    HeroTxn(8, 292500, "retail_bill", "upi", "Google Pay UPI", 12, 5),
    HeroTxn(11, 258000, "retail_bill", "upi", "Paytm UPI", 20, 15),
    HeroTxn(15, 232500, "retail_bill", "wallet", "Amazon Pay Wallet", 18, 40),
    HeroTxn(18, 262500, "retail_bill", "card", "Visa Credit", 13, 30),
    HeroTxn(6, 78000, "retail_bill", "cash", None, 10, 45),
    HeroTxn(13, 84000, "retail_bill", "cash", None, 17, 50),
    # --- baseline: cash still a third of the counter ---
    HeroTxn(28, 435000, "retail_bill", "upi", "PhonePe UPI", 11, 0),
    HeroTxn(38, 397500, "retail_bill", "card", "RuPay Debit", 19, 25),
    HeroTxn(48, 412500, "retail_bill", "upi", "Google Pay UPI", 12, 40),
    HeroTxn(58, 375000, "retail_bill", "upi", "Paytm UPI", 18, 55),
    HeroTxn(70, 427500, "retail_bill", "card", "Visa Credit", 13, 15),
    HeroTxn(82, 400500, "retail_bill", "upi", "PhonePe UPI", 20, 5),
    HeroTxn(31, 228000, "retail_bill", "cash", "Cash Drawer", 10, 30),
    HeroTxn(44, 222000, "retail_bill", "cash", "Cash Drawer", 17, 20),
    HeroTxn(57, 240000, "retail_bill", "cash", None, 11, 45),
    HeroTxn(66, 232500, "retail_bill", "cash", "Cash Drawer", 19, 35),
    HeroTxn(78, 229500, "retail_bill", "cash", "Cash Drawer", 12, 25),
    # --- settlements: clean, T+1 on time ---
    HeroTxn(21, 1760000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 45),
    HeroTxn(51, 1780000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 45),
    HeroTxn(81, 1780000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 2, 45),
    HeroTxn(10, -32000, "refund", "upi", "PhonePe UPI", 16, 10),
    HeroTxn(40, -28000, "refund", "card", "RuPay Debit", 15, 55),
]

# ---------------------------------------------------------------------------
# CTR-0004 — Metro Line-1 Andheri, TVM cluster (metro, anchor)
# Very high velocity but NCMC adoption stuck at 8% -> MOD-ETICKET
#   ticket_sale rows: 25, of which 2 are NCMC          -> 8.0% by count
#   ticket_sale Rs 90,00,000, of which NCMC 7,20,000   -> 8.0% by value
#   monthly TPV Rs 30,00,000; cash 24,84,000 = 27.6%
# ---------------------------------------------------------------------------
_CTR4_TXNS: list[HeroTxn] = [
    HeroTxn(1, 342000, "ticket_sale", "cash", "Cash Drawer", 8, 30),
    HeroTxn(2, 388000, "ticket_sale", "upi", "PhonePe UPI", 9, 10),
    HeroTxn(3, 355000, "ticket_sale", "card", "RuPay Debit", 18, 20),
    HeroTxn(5, 371000, "ticket_sale", "cash", "Cash Drawer", 8, 45),
    HeroTxn(6, 330000, "ticket_sale", "upi", "Google Pay UPI", 19, 5),
    HeroTxn(8, 396000, "ticket_sale", "card", "Visa Debit", 9, 25),
    HeroTxn(10, 348000, "ticket_sale", "cash", None, 18, 40),
    HeroTxn(12, 362000, "ticket_sale", "upi", "Paytm UPI", 8, 15),
    HeroTxn(14, 379000, "ticket_sale", "card", "RuPay Debit", 19, 30),
    HeroTxn(16, 335000, "ticket_sale", "cash", "Cash Drawer", 9, 50),
    HeroTxn(18, 401000, "ticket_sale", "upi", "PhonePe UPI", 18, 10),
    HeroTxn(20, 358000, "ticket_sale", "card", "Visa Debit", 8, 35),
    HeroTxn(24, 344000, "ticket_sale", "cash", "Cash Drawer", 19, 15),
    HeroTxn(28, 385000, "ticket_sale", "upi", "Google Pay UPI", 9, 0),
    HeroTxn(32, 367000, "ticket_sale", "card", "RuPay Debit", 18, 55),
    HeroTxn(36, 352000, "ticket_sale", "cash", None, 8, 20),
    HeroTxn(40, 374000, "ticket_sale", "upi", "Paytm UPI", 19, 40),
    HeroTxn(45, 339000, "ticket_sale", "card", "Visa Credit", 9, 30),
    HeroTxn(50, 392000, "ticket_sale", "cash", "Cash Drawer", 18, 25),
    HeroTxn(56, 361000, "ticket_sale", "upi", "PhonePe UPI", 8, 55),
    HeroTxn(62, 347000, "ticket_sale", "card", "RuPay Debit", 19, 20),
    HeroTxn(70, 383000, "ticket_sale", "upi", "Google Pay UPI", 9, 45),
    HeroTxn(80, 271000, "ticket_sale", "card", "Visa Debit", 18, 5),
    # the entire NCMC book — two taps' worth of volume, 8% of the cluster
    HeroTxn(7, 360000, "ticket_sale", "ncmc", "RuPay NCMC", 9, 15),
    HeroTxn(54, 360000, "ticket_sale", "ncmc", "RuPay NCMC", 18, 35),
    # --- settlements to Mumbai Metro One's revenue account ---
    HeroTxn(20, 2975000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 3, 0),
    HeroTxn(50, 2950000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 3, 0),
    HeroTxn(80, 2955000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 3, 0),
    HeroTxn(11, -55000, "refund", "upi", "PhonePe UPI", 16, 30),
    HeroTxn(30, 18000, "void_reissue", "cash", "Reissued Ticket", 18, 45),
]

# ---------------------------------------------------------------------------
# CTR-0005 — Shree Provision Stores, Pune (retail, standard)
# Crossed the Rs 5,00,000 GST e-invoice band with a 46% receipt gap -> MOD-BILLING
#   collections Rs 18,60,000 over 90d -> monthly TPV Rs 6,20,000 (>= Rs 5L band)
#   rows with instrument IS NULL: 12 / 26 = 46.2% by count
#   value with instrument IS NULL: 8,55,600 / 18,60,000 = 46.0% by value
#   cash Rs 8,55,600 = 46.0% and flat across the window (no spike)
# ---------------------------------------------------------------------------
_CTR5_TXNS: list[HeroTxn] = [
    # --- no bill issued (instrument NULL) ---
    HeroTxn(2, 68000, "retail_bill", "cash", None, 10, 20),
    HeroTxn(9, 74500, "retail_bill", "cash", None, 19, 5),
    HeroTxn(16, 65000, "retail_bill", "cash", None, 11, 40),
    HeroTxn(24, 79000, "retail_bill", "cash", None, 18, 30),
    HeroTxn(33, 71000, "retail_bill", "cash", None, 10, 55),
    HeroTxn(41, 76500, "retail_bill", "cash", None, 20, 10),
    HeroTxn(49, 62000, "retail_bill", "cash", None, 12, 15),
    HeroTxn(58, 83000, "retail_bill", "cash", None, 19, 45),
    HeroTxn(67, 69500, "retail_bill", "cash", None, 11, 25),
    HeroTxn(6, 72000, "retail_bill", "upi", None, 18, 50),
    HeroTxn(37, 66000, "retail_bill", "upi", None, 13, 5),
    HeroTxn(73, 69100, "retail_bill", "upi", None, 19, 35),
    # --- bill issued ---
    HeroTxn(4, 75000, "retail_bill", "upi", "PhonePe UPI", 11, 10),
    HeroTxn(12, 68000, "retail_bill", "upi", "Google Pay UPI", 18, 15),
    HeroTxn(20, 82000, "retail_bill", "card", "RuPay Debit", 12, 30),
    HeroTxn(27, 64000, "retail_bill", "upi", "Paytm UPI", 19, 20),
    HeroTxn(35, 77500, "retail_bill", "wallet", "Amazon Pay Wallet", 10, 40),
    HeroTxn(44, 70000, "retail_bill", "upi", "PhonePe UPI", 20, 0),
    HeroTxn(52, 85000, "retail_bill", "cash", "Cash Drawer", 11, 55),
    HeroTxn(60, 66500, "retail_bill", "upi", "Google Pay UPI", 18, 35),
    HeroTxn(65, 73000, "retail_bill", "card", "Visa Debit", 12, 45),
    HeroTxn(70, 79200, "retail_bill", "cash", "Cash Drawer", 19, 15),
    HeroTxn(77, 62000, "retail_bill", "upi", "Paytm UPI", 10, 25),
    HeroTxn(82, 88000, "retail_bill", "upi", "PhonePe UPI", 18, 55),
    HeroTxn(86, 71300, "retail_bill", "card", "RuPay Debit", 13, 20),
    HeroTxn(88, 42900, "retail_bill", "cash", "Cash Drawer", 11, 5),
    # --- settlements ---
    HeroTxn(25, 600000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 3, 30),
    HeroTxn(55, 595000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 3, 30),
    HeroTxn(85, 595000, "settlement_payout", "netbanking", "Billeasy Nodal T+1", 3, 30),
    HeroTxn(20, -8500, "refund", "upi", "PhonePe UPI", 16, 45),
]


def hero_counters() -> list[HeroCounter]:
    return [
        # ---------------------------------------------------------------
        # 1. GATEWAY JETTY — COUNTER 3 — fare leakage, settlement mismatch
        # ---------------------------------------------------------------
        HeroCounter(
            id="CTR-0001",
            name="Gateway Jetty — Counter 3",
            counter_type="ferry",
            city="Mumbai",
            tier="anchor",
            operator="Maharashtra Maritime Board",
            monthly_tpv=2500000,
            phone="+91-70371-48039",
            email="gateway.counter3@maritime.example.in",
            onboarded_years_ago=4,
            device_type="pos",
            pending_settlement=452700,
            avg_daily_txns=410,
            digital_share=0.39,
            device_offline_minutes=18.0,
            settlement_cycle="T+1",
            consent_ok=False,
            existing_modules=["MOD-ETICKET", "MOD-QR"],
            expected_module="MOD-RECON",
            persona_note=(
                "Cash share on Counter 3 has gone from 22% to 61% in three weeks while "
                "sailings stayed flat, and void-then-reissue entries are clustering on the "
                "evening shift. Rs 4.5L of captured fare is still unsettled. Classic "
                "fare-leakage pattern — needs reconciliation before the monthly revenue "
                "share goes to the Maritime Board."
            ),
            txns=_CTR1_TXNS,
            field_notes=[
                HeroFieldNote(
                    4,
                    "field_visit",
                    "Evening shift at Gateway Jetty Counter 3. Queue was long and the clerk "
                    "was taking cash and issuing handwritten chits instead of scanning the QR. "
                    "Counted several tickets voided and reissued within the same minute. "
                    "Flagged to the jetty supervisor — reconciliation mismatch is likely.",
                ),
                HeroFieldNote(
                    11,
                    "call",
                    "Supervisor says the ticketing app was hanging last week so staff fell "
                    "back to cash only. Asked when the settlement dispute for last month's "
                    "Rs 4.5 lakh shortfall will be closed.",
                ),
                HeroFieldNote(
                    19,
                    "ticket",
                    "Escalation raised by the Maritime Board revenue cell: captured fare "
                    "does not tie out with the T+1 payout for three consecutive days. "
                    "Reconciliation report requested.",
                ),
                HeroFieldNote(
                    46,
                    "whatsapp",
                    "Routine check-in. Counter was running smoothly on QR at that time, "
                    "digital adoption looked healthy.",
                ),
            ],
        ),
        # ---------------------------------------------------------------
        # 2. BEST DEPOT — WADALA COUNTER 1 — peak-hour device downtime
        # ---------------------------------------------------------------
        HeroCounter(
            id="CTR-0002",
            name="BEST Depot — Wadala Counter 1",
            counter_type="bus",
            city="Mumbai",
            tier="flagship",
            operator="BEST Undertaking",
            monthly_tpv=1450000,
            phone="+91-98200-41022",
            email="wadala.counter1@bestdepot.example.in",
            onboarded_years_ago=3,
            device_type="handheld",
            pending_settlement=145000,
            avg_daily_txns=260,
            digital_share=0.79,
            device_offline_minutes=240.0,
            settlement_cycle="T+1",
            existing_modules=["MOD-ETICKET"],
            expected_module="MOD-OFFLINE",
            persona_note=(
                "The handheld at Wadala Counter 1 was dead for the entire 17:00-21:00 "
                "evening peak three days ago — 240 minutes with zero recorded fares on the "
                "busiest window of the day. Roughly a third of the shifts also close without "
                "a digital receipt. Depot needs offline-first sync so fares keep recording "
                "when the network drops."
            ),
            txns=_CTR2_TXNS,
            field_notes=[
                HeroFieldNote(
                    3,
                    "ticket",
                    "Device offline 240 minutes during the evening peak (17:00-21:00) at "
                    "Wadala Counter 1. Network at the depot dropped and the handheld could "
                    "not reach the server, so conductors sold paper tickets. Fares for that "
                    "window are unrecorded.",
                ),
                HeroFieldNote(
                    6,
                    "field_visit",
                    "Depot supervisor showed the battery and connectivity log — the handheld "
                    "hangs whenever the depot Wi-Fi flaps. Printer also ran out of roll twice "
                    "last week so receipts were not issued.",
                ),
                HeroFieldNote(
                    13,
                    "call",
                    "Supervisor asked whether the device can keep issuing tickets offline and "
                    "sync later. Said BEST audit needs every fare recorded, complaint already "
                    "logged with the depot manager.",
                ),
            ],
        ),
        # ---------------------------------------------------------------
        # 3. SAHAKARI BHANDAR — DADAR — high value retail, no loyalty
        # ---------------------------------------------------------------
        HeroCounter(
            id="CTR-0003",
            name="Sahakari Bhandar — Dadar",
            counter_type="retail",
            city="Mumbai",
            tier="flagship",
            operator="Sahakari Bhandar Retail",
            monthly_tpv=1800000,
            phone="+91-98330-52217",
            email="dadar@sahakaribhandar.example.in",
            onboarded_years_ago=5,
            device_type="pos",
            pending_settlement=80000,
            avg_daily_txns=340,
            digital_share=0.91,
            device_offline_minutes=6.0,
            settlement_cycle="T+1",
            existing_modules=["MOD-BILLING", "MOD-QR"],
            expected_module="MOD-LOYALTY",
            persona_note=(
                "Rs 18L a month, 340 bills a day, and digital share has climbed from 68% to "
                "91% in a quarter — the strongest retail counter in Dadar. Settles clean on "
                "T+1 and has no loyalty module, so repeat shoppers are walking out "
                "unrewarded. Prime cross-sell."
            ),
            txns=_CTR3_TXNS,
            field_notes=[
                HeroFieldNote(
                    9,
                    "field_visit",
                    "Store manager is happy with the QR adoption — says regular shoppers now "
                    "pay digitally without being asked. Wants to know if we can give repeat "
                    "shoppers points or a festive reward.",
                ),
                HeroFieldNote(
                    27,
                    "whatsapp",
                    "Confirmed payouts have been settling on time every day this month. "
                    "Asked about expanding Billeasy to their Prabhadevi outlet.",
                ),
                HeroFieldNote(
                    52,
                    "call",
                    "Training done for two new counter staff on the billing app. Smooth "
                    "session, no open issues.",
                ),
            ],
        ),
        # ---------------------------------------------------------------
        # 4. METRO LINE-1 ANDHERI — TVM CLUSTER — NCMC adoption stuck
        # ---------------------------------------------------------------
        HeroCounter(
            id="CTR-0004",
            name="Metro Line-1 Andheri — TVM Cluster",
            counter_type="metro",
            city="Mumbai",
            tier="anchor",
            operator="Mumbai Metro One",
            monthly_tpv=3000000,
            phone="+91-98670-30114",
            email="andheri.tvm@mumbaimetroone.example.in",
            onboarded_years_ago=2,
            device_type="tvm",
            pending_settlement=420000,
            avg_daily_txns=980,
            digital_share=0.72,
            device_offline_minutes=35.0,
            settlement_cycle="T+1",
            existing_modules=["MOD-QR", "MOD-ANALYTICS"],
            expected_module="MOD-ETICKET",
            persona_note=(
                "The busiest cluster on the patch — Rs 30L a month across roughly 980 "
                "transactions a day — but only 8% of fare value moves on NCMC cards and "
                "27% is still cash at the machine. Huge headroom for QR + NCMC e-ticketing "
                "under One Nation One Card."
            ),
            txns=_CTR4_TXNS,
            field_notes=[
                HeroFieldNote(
                    5,
                    "field_visit",
                    "Peak-hour observation at Andheri TVM cluster. Long queues at the cash "
                    "machines while the two card readers sat idle — most commuters do not "
                    "know NCMC taps are accepted here. Signage is missing.",
                ),
                HeroFieldNote(
                    14,
                    "call",
                    "Station controller asked about the AFC gate integration timeline and "
                    "whether NCMC top-up can happen at the same counter.",
                ),
                HeroFieldNote(
                    38,
                    "ticket",
                    "Ridership up 12% month on month; controller wants a plan to move queues "
                    "off cash before the monsoon rush.",
                ),
            ],
        ),
        # ---------------------------------------------------------------
        # 5. SHREE PROVISION STORES — PUNE — GST band crossed, no bills
        # ---------------------------------------------------------------
        HeroCounter(
            id="CTR-0005",
            name="Shree Provision Stores — Pune",
            counter_type="retail",
            city="Pune",
            tier="standard",
            operator="Shree Provision Stores",
            monthly_tpv=620000,
            phone="+91-98220-71905",
            email="shreeprovision.pune@example.in",
            onboarded_years_ago=2,
            device_type="qr_standee",
            pending_settlement=70000,
            avg_daily_txns=62,
            digital_share=0.54,
            device_offline_minutes=12.0,
            settlement_cycle="T+2",
            existing_modules=["MOD-QR"],
            expected_module="MOD-BILLING",
            persona_note=(
                "Crossed Rs 5,00,000 monthly TPV two months ago and is now sitting in the GST "
                "e-invoice band, but 46% of the counter's value closes with no digital bill "
                "at all. Owner is exposed on compliance and does not know it — the fix is a "
                "billing module, not a lecture."
            ),
            txns=_CTR5_TXNS,
            field_notes=[
                HeroFieldNote(
                    7,
                    "field_visit",
                    "Owner is issuing a paper slip for most cash sales and does not print a "
                    "GST bill. Explained the e-invoice threshold; he was not aware his monthly "
                    "turnover had crossed it.",
                ),
                HeroFieldNote(
                    21,
                    "whatsapp",
                    "GST query from the owner's accountant — asked what a compliant B2C "
                    "dynamic QR bill has to show and whether Billeasy can generate it.",
                ),
                HeroFieldNote(
                    34,
                    "call",
                    "Payout delayed query: owner asked why his settlement lands on T+2 and "
                    "whether moving to T+1 is possible once billing is in place.",
                ),
            ],
        ),
    ]


def today() -> date:
    return datetime.utcnow().date()


def days_ago(n: int) -> str:
    return (today() - timedelta(days=n)).isoformat()
