-- ===========================================================================
-- counter-copilot — SQLite schema
-- Same logical shape as the Databricks Delta tables.
-- Domain: Billeasy offline payments & transit ticketing counters.
-- ===========================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS counters (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    counter_type        TEXT NOT NULL,            -- retail | ferry | bus | metro
    city                TEXT NOT NULL,
    tier                TEXT NOT NULL,            -- nano | standard | flagship | anchor
    operator            TEXT NOT NULL,            -- merchant or transit agency
    monthly_tpv         REAL NOT NULL,            -- total payment volume, Rs / month
    onboarded_date      TEXT NOT NULL,            -- ISO date
    kyc_status          TEXT NOT NULL DEFAULT 'verified',
    phone               TEXT NOT NULL,
    email               TEXT,
    settlement_cycle    TEXT NOT NULL DEFAULT 'T+1',   -- T+1 | T+2 | weekly
    -- DPDP (India) business-consent for outreach: whether the merchant opted in to
    -- WhatsApp / call nudges. Gates draft generation — a top pitch never outweighs it.
    consent_ok          INTEGER NOT NULL DEFAULT 1,    -- 1 = consented, 0 = no consent
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_counters_city ON counters(city);
CREATE INDEX IF NOT EXISTS idx_counters_tier ON counters(tier);

-- Counter health / settlement rollup. Joined onto `counters` to produce the
-- enriched fields on the Counter model (pending_settlement, avg_daily_txns,
-- digital_share). One row per live counter device.
CREATE TABLE IF NOT EXISTS counter_health (
    id                  TEXT PRIMARY KEY,
    counter_id          TEXT NOT NULL REFERENCES counters(id),
    device_type         TEXT NOT NULL,            -- pos | tvm | handheld | qr_standee
    pending_settlement  REAL NOT NULL,            -- Rs awaiting payout
    avg_daily_txns      REAL NOT NULL,
    digital_share       REAL NOT NULL,            -- 0..1 share of TPV on digital rails
    -- Device uptime telemetry, as a real POS/AFC estate reports it. Minutes the terminal
    -- was unreachable during peak windows over the trailing period. Every dark minute at
    -- a transit counter is an unrecorded fare, so this is a first-class leakage input
    -- rather than something inferred from gaps between transactions.
    device_offline_minutes REAL NOT NULL DEFAULT 0,
    activated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_counter_health_counter ON counter_health(counter_id);

CREATE TABLE IF NOT EXISTS transactions (
    id                  TEXT PRIMARY KEY,
    counter_id          TEXT NOT NULL REFERENCES counters(id),
    ts                  TEXT NOT NULL,
    amount              REAL NOT NULL,            -- positive = collection/payout, negative = refund/chargeback
    category            TEXT NOT NULL,            -- ticket_sale | retail_bill | refund | void_reissue | settlement_payout | chargeback | topup | other
    channel             TEXT NOT NULL,            -- upi | card | cash | ncmc | wallet | netbanking
    instrument          TEXT                      -- e.g. 'PhonePe UPI', 'RuPay NCMC'. NULL = no GST bill / e-ticket issued (receipt issuance gap)
);

CREATE INDEX IF NOT EXISTS idx_txn_counter_ts ON transactions(counter_id, ts);
CREATE INDEX IF NOT EXISTS idx_txn_category   ON transactions(category);

CREATE TABLE IF NOT EXISTS modules (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    category            TEXT NOT NULL,            -- billing | ticketing | payments | reconciliation | loyalty | engagement | analytics
    take_rate           REAL,                     -- % commission per transaction
    min_monthly_tpv     REAL,
    min_daily_txns      INTEGER,
    max_daily_txns      INTEGER,
    description         TEXT,
    eligibility_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS counter_modules (
    counter_id          TEXT NOT NULL REFERENCES counters(id),
    module_id           TEXT NOT NULL REFERENCES modules(id),
    activated_at        TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',
    PRIMARY KEY (counter_id, module_id)
);

CREATE TABLE IF NOT EXISTS field_notes (
    id                  TEXT PRIMARY KEY,
    counter_id          TEXT NOT NULL REFERENCES counters(id),
    ts                  TEXT NOT NULL,
    channel             TEXT NOT NULL,            -- field_visit | call | whatsapp | email | ticket
    summary             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_field_notes_counter ON field_notes(counter_id);

-- --- Runtime tables (always SQLite, never Databricks) ---

CREATE TABLE IF NOT EXISTS sessions (
    id                  TEXT PRIMARY KEY,
    manager_id          TEXT NOT NULL DEFAULT 'rohan',
    title               TEXT,
    state_json          TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role                TEXT NOT NULL,            -- user | assistant | system
    content             TEXT NOT NULL,
    payload_json        TEXT,
    ts                  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, ts);

CREATE TABLE IF NOT EXISTS agent_traces (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    node                TEXT NOT NULL,
    input_json          TEXT,
    output_json         TEXT,
    llm_route           TEXT,
    fallback_reason     TEXT,
    source              TEXT,
    latency_ms          INTEGER,
    ts                  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_traces_session ON agent_traces(session_id, ts);

CREATE TABLE IF NOT EXISTS outreach_drafts (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    counter_id          TEXT NOT NULL REFERENCES counters(id),
    module_id           TEXT NOT NULL REFERENCES modules(id),
    channel             TEXT NOT NULL DEFAULT 'whatsapp',
    message             TEXT NOT NULL,
    score               REAL,
    rationale_json      TEXT,
    compliance_json     TEXT,
    status              TEXT NOT NULL DEFAULT 'draft',   -- draft | approved | sent | rejected
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_drafts_session ON outreach_drafts(session_id);

CREATE TABLE IF NOT EXISTS tool_cache (
    cache_key           TEXT PRIMARY KEY,
    payload_json        TEXT NOT NULL,
    created_at          INTEGER NOT NULL          -- unix seconds
);
