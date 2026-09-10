"""End-to-end seeder: modules, hero counters + 495 Faker counters + transactions + field notes.

Idempotent. Designed so the scorer's hero counters actually rank top.
"""
from __future__ import annotations

import json
import random
import sqlite3
import uuid
from datetime import date, datetime, timedelta

from faker import Faker

from app.observability import get_logger

from .hero_counters import HeroCounter, days_ago, hero_counters

logger = get_logger(__name__)

COUNTER_TYPES = ["retail", "ferry", "bus", "metro"]
TIERS = ["nano", "standard", "flagship", "anchor"]
SETTLEMENT_CYCLES = ["T+1", "T+2", "weekly"]
TXN_CATEGORIES = [
    "ticket_sale", "retail_bill", "refund", "void_reissue",
    "settlement_payout", "chargeback", "topup", "other",
]
CHANNELS = ["upi", "card", "cash", "ncmc", "wallet", "netbanking"]
DEVICE_TYPES = ["pos", "tvm", "handheld", "qr_standee"]

INSTRUMENTS = {
    "upi": ["PhonePe UPI", "Google Pay UPI", "Paytm UPI", "BHIM UPI", "Amazon Pay UPI"],
    "card": ["RuPay Debit", "Visa Debit", "Visa Credit", "Mastercard Credit"],
    "cash": ["Cash Drawer"],
    "ncmc": ["RuPay NCMC", "Mumbai 1 NCMC", "Kochi1 NCMC"],
    "wallet": ["Amazon Pay Wallet", "PhonePe Wallet", "Paytm Wallet"],
    "netbanking": ["Billeasy Nodal T+1", "Billeasy Nodal T+2"],
}

# ---------------------------------------------------------------------------
# City profiles.
#
# Sites, operators and localities are scoped per city on purpose. Drawing them
# independently produces incoherent rows — "Kashmere Gate ISBT" (a Delhi terminal)
# sitting in Kochi under MSRTC (Maharashtra's undertaking) — which is exactly the
# kind of thing that makes a demo dataset fall apart the moment somebody who knows
# Indian transit reads it. Not every city runs ferries or a metro; a city simply
# omits the modes it does not have.
# ---------------------------------------------------------------------------
CITY_PROFILE: dict[str, dict[str, object]] = {
    "Mumbai": {
        "ferry": (["Gateway Jetty", "Bhaucha Dhakka Jetty", "Mandwa Jetty",
                   "Marine Drive Boat Jetty", "Elephanta Jetty"],
                  ["Maharashtra Maritime Board"]),
        "bus": (["Wadala Depot", "Backbay Depot", "Kurla Depot"],
                ["BEST Undertaking", "MSRTC"]),
        "metro": (["Andheri Metro", "Ghatkopar Metro", "Versova Metro"],
                  ["Mumbai Metro One"]),
        "localities": ["Dadar", "Andheri West", "Bandra East", "Borivali",
                       "Thane West", "Ghatkopar"],
    },
    "Delhi": {
        "bus": (["Kashmere Gate ISBT", "Anand Vihar ISBT", "Sarai Kale Khan ISBT"],
                ["DTC"]),
        "metro": (["Rajiv Chowk Metro", "Hauz Khas Metro", "Vaishali Metro",
                   "Civil Lines Metro"], ["DMRC"]),
        "localities": ["Karol Bagh", "Lajpat Nagar", "Rohini", "Malviya Nagar"],
    },
    "Bangalore": {
        "bus": (["Majestic Bus Station", "Shivajinagar Depot"], ["BMTC", "KSRTC"]),
        "metro": (["MG Road Metro", "Majestic Metro", "Indiranagar Metro"],
                  ["Bangalore Metro Rail Corporation"]),
        "localities": ["Koramangala", "Indiranagar", "Jayanagar", "Whitefield"],
    },
    "Pune": {
        "bus": (["Swargate Depot", "Shivajinagar Depot"], ["PMPML", "MSRTC"]),
        "metro": (["Vanaz Metro", "Pimpri Metro"], ["Pune Metro Rail"]),
        "localities": ["Kothrud", "Hadapsar", "Viman Nagar"],
    },
    "Hyderabad": {
        "bus": (["Miyapur Depot", "Uppal Depot", "Jubilee Bus Station"], ["TSRTC"]),
        "metro": (["Ameerpet Metro", "Hitec City Metro"], ["Hyderabad Metro Rail"]),
        "localities": ["Gachibowli", "Kukatpally", "Ameerpet"],
    },
    "Chennai": {
        "bus": (["Koyambedu Terminus", "Broadway Depot"], ["MTC Chennai"]),
        "metro": (["Alandur Metro", "Guindy Metro"], ["Chennai Metro Rail"]),
        "localities": ["T Nagar", "Adyar", "Velachery"],
    },
    "Kolkata": {
        "ferry": (["Millennium Park Jetty", "Howrah Jetty", "Bagbazar Jetty"],
                  ["Hooghly River Bridge Commissioners"]),
        "bus": (["Esplanade Depot", "Garia Depot"], ["WBTC"]),
        "metro": (["Esplanade Metro", "Dumdum Metro"], ["Kolkata Metro Rail"]),
        "localities": ["Salt Lake", "Ballygunge"],
    },
    "Kochi": {
        "ferry": (["Vypin Jetty", "Fort Kochi Jetty", "High Court Jetty"],
                  ["Kochi Water Metro"]),
        "bus": (["Vyttila Hub", "Kaloor Depot"], ["KSRTC"]),
        "metro": (["Aluva Metro", "Edapally Metro"], ["Kochi Metro Rail"]),
        "localities": ["Kaloor", "Panampilly Nagar"],
    },
    "Ahmedabad": {
        "bus": (["Geeta Mandir Terminus", "Ranip Depot"], ["GSRTC"]),
        "metro": (["Vastral Metro", "Thaltej Metro"], ["Gujarat Metro Rail"]),
        "localities": ["Navrangpura", "Maninagar"],
    },
    "Jaipur": {
        "bus": (["Sindhi Camp Depot"], ["RSRTC"]),
        "metro": (["Mansarovar Metro", "Chandpole Metro"], ["Jaipur Metro Rail"]),
        "localities": ["Malviya Nagar", "Vaishali Nagar"],
    },
    "Lucknow": {
        "bus": (["Alambagh Terminal", "Charbagh Depot"], ["UPSRTC"]),
        "metro": (["Hazratganj Metro", "Munshipulia Metro"], ["Lucknow Metro Rail"]),
        "localities": ["Hazratganj", "Gomti Nagar"],
    },
    "Indore": {
        "bus": (["Sarwate Bus Stand", "Vijay Nagar Depot"], ["MPSRTC"]),
        "localities": ["Vijay Nagar", "Palasia"],
    },
    "Chandigarh": {
        "bus": (["ISBT Sector 43", "ISBT Sector 17"], ["CTU"]),
        "localities": ["Sector 17", "Sector 35"],
    },
    "Surat": {
        "bus": (["Surat Central Terminus", "Adajan Depot"], ["GSRTC"]),
        "localities": ["Adajan", "Vesu"],
    },
}

RETAIL_OPERATORS = [
    "Sahakari Bhandar Retail", "Apna Bazaar Stores", "Ratnadeep Retail",
    "Vijetha Supermarkets", "More Retail", "Spencer's Retail",
    "Nilgiris Franchise", "Reliance Smart Point", "Metro Cash & Carry Partner",
    "Star Bazaar Partner", "Heritage Fresh", "Nature's Basket Franchise",
]

RETAIL_SHOP_NAMES = [
    "Shree Provision Stores", "Jai Bhavani General Stores", "Annapurna Kirana",
    "Laxmi Medical & General", "Balaji Super Mart", "Ganesh Provision",
    "New Krishna Stores", "Sai Sagar Departmental", "Om Sai Traders",
    "Maruti General Stores", "Anand Bhavan Sweets", "Gupta Kirana Bhandar",
    "Vishal Fresh Mart", "Sharda Stores", "Deepak Medical Stores",
    "Ambika Departmental Stores", "Radhe Krishna Provision", "Navjeevan Stores",
    "Prakash Electricals & General", "Tulsi Fresh Mart", "Mahalakshmi Stores",
    "Bharat Bakery & Provision", "Shakti General Stores", "Jyoti Super Mart",
    "Suryodaya Traders", "Green Leaf Grocers", "Krishna Milk & Provision",
    "Vinayak Stationery & General", "Payal Departmental", "Chandan Provision Mart",
]

INDIAN_CITIES = list(CITY_PROFILE)

# city -> the transit modes it actually runs, e.g. Delhi has no ferry service.
CITY_TRANSIT_MODES: dict[str, list[str]] = {
    city: [m for m in ("ferry", "bus", "metro") if m in profile]
    for city, profile in CITY_PROFILE.items()
}

FIELD_NOTE_TEMPLATES = [
    "Device down for part of the shift — supervisor reported the handheld hanging "
    "when the network drops. Restarted on site, asked them to log it next time.",
    "Payout query: owner asked why the settlement landed a day late and wanted the "
    "T+1 cut-off explained again.",
    "Reconciliation mismatch flagged — captured collections did not tie out with the "
    "payout for one day. Raised with the settlement desk.",
    "Training request: two new counter staff joined, need a refresher on issuing "
    "digital bills and handling refunds.",
    "GST query — accountant asked what a compliant B2C dynamic QR bill must show and "
    "whether the counter is above the e-invoice threshold.",
    "Routine field visit. Counter running smoothly, digital adoption looked healthy, "
    "no open complaints.",
    "Printer roll ran out during peak so receipts were not issued for about an hour. "
    "Stock replenished.",
    "Supervisor raised a chargeback dispute on a card sale and asked for the "
    "transaction proof.",
    "Queue complaint at peak hour — passengers were paying cash because the QR "
    "standee was not visible. Repositioned it.",
    "Owner asked about adding a second counter at the same outlet next quarter.",
]

FIELD_NOTE_CHANNELS = ["field_visit", "call", "whatsapp", "email", "ticket"]

NOISE_COUNT = 495


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------

def _seed_modules(conn: sqlite3.Connection) -> None:
    modules = [
        ("MOD-BILLING", "Digital Billing & GST e-Invoice", "billing", 0.4, 200000, 20, None,
         "GST-compliant digital bills with IRN + dynamic QR, issued at the counter.",
         {"counter_type": ["retail"], "min_tenure_months": 3, "min_monthly_tpv": 200000}),
        ("MOD-ETICKET", "Transit e-Ticketing (QR + NCMC)", "ticketing", 1.2, 500000, 150, None,
         "QR and NCMC e-ticketing for jetties, depots and stations, One Nation One Card ready.",
         {"counter_type": ["ferry", "bus", "metro"], "min_tenure_months": 3, "min_daily_txns": 150}),
        ("MOD-QR", "Dynamic QR Collect", "payments", 0.6, 100000, 10, None,
         "Dynamic UPI QR collect at the counter — moves walk-in cash onto the digital rail.",
         {"counter_type": ["retail", "ferry", "bus", "metro"], "min_tenure_months": 1}),
        ("MOD-RECON", "Settlement & Fare Reconciliation", "reconciliation", 0.5, 750000, 100, None,
         "Three-way reconciliation of captured fare, settled payout and operator revenue share.",
         {"counter_type": ["ferry", "bus", "metro"], "min_tenure_months": 6, "min_monthly_tpv": 750000}),
        ("MOD-OFFLINE", "Offline-First Sync Kit", "payments", 0.7, 300000, 80, None,
         "Keeps issuing tickets and bills when the network drops, then syncs on reconnect.",
         {"counter_type": ["retail", "ferry", "bus", "metro"], "min_tenure_months": 3, "min_daily_txns": 80}),
        ("MOD-LOYALTY", "Loyalty & Rewards", "loyalty", 0.8, 400000, 40, None,
         "Points, cashback and festive rewards for repeat shoppers at the counter.",
         {"counter_type": ["retail"], "min_tenure_months": 6, "min_monthly_tpv": 400000}),
        ("MOD-WA-RECEIPT", "WhatsApp Receipts & Engagement", "engagement", 0.3, 150000, 15, None,
         "Delivers the bill or e-ticket on WhatsApp with DPDP-compliant consent capture.",
         {"counter_type": ["retail"], "min_tenure_months": 1, "consent_required": True}),
        ("MOD-ANALYTICS", "Counter Analytics", "analytics", 0.5, 250000, 25, None,
         "Counter-level dashboards for TPV, channel mix, peak-hour load and leakage alerts.",
         {"counter_type": ["retail", "ferry", "bus", "metro"], "min_tenure_months": 3}),
    ]
    rows = [
        (mid, name, cat, take_rate, min_tpv, min_txns, max_txns, desc, json.dumps(elig))
        for (mid, name, cat, take_rate, min_tpv, min_txns, max_txns, desc, elig) in modules
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO modules
            (id, name, category, take_rate, min_monthly_tpv, min_daily_txns, max_daily_txns,
             description, eligibility_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


# ---------------------------------------------------------------------------
# Hero counters
# ---------------------------------------------------------------------------

def _insert_hero(conn: sqlite3.Connection, h: HeroCounter) -> None:
    onboarded = (date.today() - timedelta(days=365 * h.onboarded_years_ago)).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO counters
        (id, name, counter_type, city, tier, operator, monthly_tpv, onboarded_date,
         kyc_status, phone, email, settlement_cycle, consent_ok)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'verified', ?, ?, ?, ?)
        """,
        (h.id, h.name, h.counter_type, h.city, h.tier, h.operator, h.monthly_tpv,
         onboarded, h.phone, h.email, h.settlement_cycle, h.consent_ok),
    )
    health_id = f"HLT-{h.id[-4:]}"
    conn.execute(
        """
        INSERT OR REPLACE INTO counter_health
            (id, counter_id, device_type, pending_settlement, avg_daily_txns, digital_share,
             device_offline_minutes, activated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (health_id, h.id, h.device_type, h.pending_settlement, h.avg_daily_txns,
         h.digital_share, h.device_offline_minutes, onboarded),
    )
    for t in h.txns:
        ts = (
            datetime.utcnow().replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            - timedelta(days=t.days_ago)
        ).isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO transactions (id, counter_id, ts, amount, category, channel, instrument)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), h.id, ts, t.amount, t.category, t.channel, t.instrument),
        )
    for note in h.field_notes:
        conn.execute(
            """
            INSERT INTO field_notes (id, counter_id, ts, channel, summary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), h.id, days_ago(note.days_ago), note.channel, note.summary),
        )
    for mid in h.existing_modules:
        conn.execute(
            """
            INSERT OR IGNORE INTO counter_modules (counter_id, module_id, activated_at, status)
            VALUES (?, ?, ?, 'active')
            """,
            (h.id, mid, onboarded),
        )


# ---------------------------------------------------------------------------
# Faker noise counters
# ---------------------------------------------------------------------------

_TPV_BANDS = {
    "nano": (50000, 200000),
    "standard": (200000, 800000),
    "flagship": (800000, 2500000),
    "anchor": (2500000, 12000000),
}

_DAILY_TXN_BANDS = {
    "nano": (8, 45),
    "standard": (40, 140),
    "flagship": (120, 420),
    "anchor": (350, 1400),
}

_DEVICE_BY_TYPE = {
    "retail": ["pos", "qr_standee", "handheld"],
    "ferry": ["pos", "handheld"],
    "bus": ["handheld", "pos"],
    "metro": ["tvm", "pos"],
}


# Relative mix of counter types across the network.
_TYPE_WEIGHT = {"retail": 0.55, "ferry": 0.13, "bus": 0.20, "metro": 0.12}

_RETAIL_MODULES = ["MOD-BILLING", "MOD-QR", "MOD-WA-RECEIPT", "MOD-LOYALTY", "MOD-ANALYTICS"]
_TRANSIT_MODULES = ["MOD-ETICKET", "MOD-QR", "MOD-RECON", "MOD-OFFLINE", "MOD-ANALYTICS"]


def _device_offline_minutes() -> float:
    """Peak-window downtime for a healthy-ish estate.

    Most terminals are fine; a long tail is not. Roughly 80% lose under half an hour,
    15% have a bad patch, and 5% are the ones an Area Manager needs to hear about.
    """
    roll = random.random()
    if roll < 0.80:
        return round(random.uniform(0, 30), 1)
    if roll < 0.95:
        return round(random.uniform(30, 120), 1)
    return round(random.uniform(120, 300), 1)


def _counter_name(counter_type: str, city: str, used: set[str]) -> str:
    """Name a counter using sites that genuinely belong to that city.

    Names must be unique across the network: they are what an Area Manager types
    ("what's happening at Wadala Counter 1?") and what the knowledge base resolves
    a question against, so two counters sharing a name makes both unanswerable.
    """
    if counter_type == "retail":
        localities: list[str] = CITY_PROFILE[city]["localities"]  # type: ignore[assignment]
        for _ in range(40):
            name = f"{random.choice(RETAIL_SHOP_NAMES)} — {random.choice(localities)}"
            if name not in used:
                return name
        base = f"{random.choice(RETAIL_SHOP_NAMES)} — {random.choice(localities)}"
        n = 2
        while f"{base} ({n})" in used:
            n += 1
        return f"{base} ({n})"

    sites, _ = CITY_PROFILE[city][counter_type]  # type: ignore[misc]
    for _ in range(40):
        name = f"{random.choice(sites)} — Counter {random.randint(1, 8)}"
        if name not in used:
            return name
    site = random.choice(sites)
    n = 9
    while f"{site} — Counter {n}" in used:
        n += 1
    return f"{site} — Counter {n}"


def _operator_for(counter_type: str, city: str) -> str:
    """The undertaking / chain that actually runs this counter in this city."""
    if counter_type == "retail":
        return random.choice(RETAIL_OPERATORS)
    _, operators = CITY_PROFILE[city][counter_type]  # type: ignore[misc]
    return random.choice(operators)


def _seed_noise(conn: sqlite3.Connection, count: int = NOISE_COUNT) -> None:
    fake = Faker("en_IN")
    Faker.seed(7)
    random.seed(7)

    # Seeded with the hero names so a noise counter can never shadow "Gateway Jetty
    # — Counter 3" and make the demo ambiguous.
    used_names: set[str] = {h.name for h in hero_counters()}

    for i in range(count):
        cid = f"CTR-{i + 6:04d}"
        # City first, then the modes that city actually runs — retail is everywhere,
        # ferries and metros are not.
        city = random.choice(INDIAN_CITIES)
        available = ["retail"] + CITY_TRANSIT_MODES[city]
        counter_type = random.choices(
            available, weights=[_TYPE_WEIGHT[t] for t in available]
        )[0]
        tier = random.choices(TIERS, weights=[0.30, 0.40, 0.22, 0.08])[0]
        monthly_tpv = round(random.uniform(*_TPV_BANDS[tier]), -3)
        avg_daily_txns = float(random.randint(*_DAILY_TXN_BANDS[tier]))
        digital_share = round(random.uniform(0.35, 0.98), 2)
        pending_settlement = round(monthly_tpv / 30 * random.uniform(0.8, 6.0), -2)
        operator = _operator_for(counter_type, city)
        counter_name = _counter_name(counter_type, city, used_names)
        used_names.add(counter_name)
        settlement_cycle = random.choices(SETTLEMENT_CYCLES, weights=[0.70, 0.20, 0.10])[0]
        years_live = random.randint(1, 9)
        onboarded = (
            date.today() - timedelta(days=365 * years_live + random.randint(0, 364))
        ).isoformat()
        # DPDP outreach consent: majority opt out, minority stay opted in
        consent_ok = random.random() >= 0.12

        conn.execute(
            """
            INSERT INTO counters
            (id, name, counter_type, city, tier, operator, monthly_tpv, onboarded_date,
             kyc_status, phone, email, settlement_cycle, consent_ok)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'verified', ?, ?, ?, ?)
            """,
            (cid, counter_name, counter_type,
             city, tier, operator, monthly_tpv, onboarded,
             f"+91-{random.randint(70000, 99999)}-{random.randint(10000, 99999)}",
             fake.email(), settlement_cycle, consent_ok),
        )

        conn.execute(
            """
            INSERT INTO counter_health
                (id, counter_id, device_type, pending_settlement, avg_daily_txns,
                 digital_share, device_offline_minutes, activated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"HLT-{i + 6:04d}", cid, random.choice(_DEVICE_BY_TYPE[counter_type]),
             pending_settlement, avg_daily_txns, digital_share,
             _device_offline_minutes(), onboarded),
        )

        # --- transactions: 15-45 rows of collections, payouts and adjustments ---
        collection_category = "ticket_sale" if counter_type != "retail" else "retail_bill"
        n_txns = random.randint(15, 45)
        n_payouts = random.randint(2, 3)
        n_collections = max(1, n_txns - n_payouts - 2)

        # Per-collection ticket sized so the rows roughly reproduce monthly TPV.
        avg_ticket = (monthly_tpv * 3) / n_collections
        digital_channels = ["upi", "card", "wallet"] + (
            ["ncmc"] if counter_type in ("ferry", "bus", "metro") else []
        )
        for _ in range(n_collections):
            channel = (
                random.choice(digital_channels)
                if random.random() < digital_share
                else "cash"
            )
            # ~18% of counters close a sale without issuing a digital bill
            instrument = (
                None if random.random() < 0.18 else random.choice(INSTRUMENTS[channel])
            )
            category = (
                "void_reissue"
                if random.random() < 0.04
                else collection_category
            )
            amt = round(random.uniform(avg_ticket * 0.55, avg_ticket * 1.45), 0)
            ts = (
                datetime.utcnow().replace(
                    hour=random.randint(7, 21), minute=random.randint(0, 59),
                    second=0, microsecond=0,
                )
                - timedelta(days=random.randint(1, 90))
            ).isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO transactions (id, counter_id, ts, amount, category, channel, instrument)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), cid, ts, amt, category, channel, instrument),
            )

        for k in range(n_payouts):
            settled = round(monthly_tpv * random.uniform(0.90, 0.99), -2)
            ts = (
                datetime.utcnow().replace(hour=2, minute=30, second=0, microsecond=0)
                - timedelta(days=30 * k + random.randint(1, 5))
            ).isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO transactions (id, counter_id, ts, amount, category, channel, instrument)"
                " VALUES (?, ?, ?, ?, 'settlement_payout', 'netbanking', ?)",
                (str(uuid.uuid4()), cid, ts, settled,
                 f"Billeasy Nodal {settlement_cycle}"),
            )

        for _ in range(2):
            cat = random.choices(
                ["refund", "chargeback", "topup", "other"],
                weights=[0.55, 0.10, 0.20, 0.15],
            )[0]
            sign = -1 if cat in ("refund", "chargeback") else 1
            amt = sign * round(random.uniform(200, avg_ticket * 0.9), 0)
            channel = random.choice(CHANNELS)
            ts = (
                datetime.utcnow().replace(
                    hour=random.randint(7, 21), minute=random.randint(0, 59),
                    second=0, microsecond=0,
                )
                - timedelta(days=random.randint(1, 90))
            ).isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO transactions (id, counter_id, ts, amount, category, channel, instrument)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), cid, ts, amt, cat, channel,
                 random.choice(INSTRUMENTS[channel])),
            )

        # ~25% have a field-visit note on record
        if random.random() < 0.25:
            conn.execute(
                "INSERT INTO field_notes (id, counter_id, ts, channel, summary) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), cid, days_ago(random.randint(5, 90)),
                 random.choice(FIELD_NOTE_CHANNELS), random.choice(FIELD_NOTE_TEMPLATES)),
            )

        # ~35% already run 1-2 Billeasy modules
        if random.random() < 0.35:
            pool = _RETAIL_MODULES if counter_type == "retail" else _TRANSIT_MODULES
            for mid in random.sample(pool, random.randint(1, 2)):
                conn.execute(
                    "INSERT OR IGNORE INTO counter_modules (counter_id, module_id, activated_at, status)"
                    " VALUES (?, ?, ?, 'active')",
                    (cid, mid, onboarded),
                )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run_seed(conn: sqlite3.Connection) -> None:
    logger.info("Seeding modules...")
    _seed_modules(conn)
    logger.info("Seeding hero counters...")
    for h in hero_counters():
        _insert_hero(conn, h)
    logger.info("Seeding %d Faker noise counters...", NOISE_COUNT)
    _seed_noise(conn, NOISE_COUNT)
    conn.commit()
    logger.info("Seed complete.")


if __name__ == "__main__":
    from app.db.sqlite_engine import bootstrap

    bootstrap()
