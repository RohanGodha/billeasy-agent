/** Mirrors the backend Pydantic models (Counter Copilot domain) in TypeScript. */

/** Retail outlet, or a government transit ticketing counter. */
export type CounterType = 'retail' | 'ferry' | 'bus' | 'metro';

/** Network tier — sized by monthly TPV and daily transaction volume. */
export type CounterTier = 'nano' | 'standard' | 'flagship' | 'anchor';

/** Severity band for revenue leakage. `elevated` and above needs a supervisor call. */
export type LeakageBand = 'clear' | 'watch' | 'elevated' | 'severe';

export interface Counter {
  id: string;
  name: string;
  counter_type: CounterType;
  city: string;
  tier: CounterTier;
  /** Merchant or transit agency that operates the counter. */
  operator: string;
  /** Total payment volume routed through the counter, ₹ per month. */
  monthly_tpv: number;
  onboarded_date: string;
  /** Merchant KYC state. */
  kyc_status: string;
  /** Supervisor / outlet owner phone. */
  phone: string;
  email?: string | null;
  /** "T+1" | "T+2" | "weekly". */
  settlement_cycle: string;

  /** Enriched from the counter health / settlement tables. */
  pending_settlement?: number | null;
  avg_daily_txns?: number | null;
  /** 0..1 share of TPV captured on digital rails. */
  digital_share?: number | null;
}

export interface Transaction {
  id: string;
  counter_id: string;
  ts: string;
  amount: number;
  /** ticket_sale | retail_bill | refund | void_reissue | settlement_payout | chargeback | topup | other */
  category: string;
  /** upi | card | cash | ncmc | wallet | netbanking */
  channel: string;
  /** Payment instrument, e.g. "PhonePe UPI", "RuPay NCMC". */
  instrument?: string | null;
}

/** A Billeasy SaaS module / SKU that can run on a counter. */
export interface Module {
  id: string;
  name: string;
  /** billing | ticketing | payments | reconciliation | loyalty | engagement | analytics */
  category: string;
  /** % commission per transaction. */
  take_rate?: number | null;
  min_monthly_tpv?: number | null;
  min_daily_txns?: number | null;
  max_daily_txns?: number | null;
  description?: string | null;
}

/** A module already live on a counter. */
export interface CounterModule {
  module_id: string;
  name: string;
  category: string;
  status: string;
  activated_at: string;
}

/** Field-visit note or support ticket logged against a counter. */
export interface FieldNote {
  id: string;
  counter_id: string;
  ts: string;
  channel: string;
  summary: string;
}

export interface ScoreBreakdown {
  feature: string;
  value: number;
  contribution: number;
  direction: 'positive' | 'negative' | 'neutral';
  rationale: string;
  kind?: 'value' | 'propensity';
}

/** Domain-model candidate as returned by the scoring layer. */
export interface Candidate {
  counter: Counter;
  value_score: number;
  propensity_score: number;
  composite_score: number;
  /** The money signal — revenue drifting off the digital rail, 0..1 severity. */
  leakage_risk: number;
  leakage_band?: LeakageBand;
  recommended_module_id?: string | null;
  recommended_module_name?: string | null;
  feature_contributions: ScoreBreakdown[];
  rationale: string;
  citations: string[];
}

/**
 * Flattened candidate as streamed on the `candidate` SSE event. The agent
 * denormalises the counter onto the record so the panel can render without a
 * second fetch.
 */
export interface CandidateRecord {
  counter_id: string;
  name: string;
  city: string;
  tier: string;
  counter_type?: string;
  operator?: string;
  monthly_tpv?: number | null;
  avg_daily_txns?: number | null;
  value_score: number;
  propensity_score: number;
  composite_score: number;
  recommended_module_id: string;
  recommended_module_name: string;
  top_features: ScoreBreakdown[];
  rationale: string;
  citations: string[];
  /** Sentiment read off the counter's field notes. */
  sentiment?: 'positive' | 'neutral' | 'negative';
  escalate?: boolean;
  /** Revenue-leakage severity in 0..1, computed from transaction evidence. */
  leakage_risk?: number;
  leakage_band?: LeakageBand;
  /** Per-feature contributions behind `leakage_risk`, largest first. */
  leakage_features?: ScoreBreakdown[];
  opportunity_value?: number | null;
  next_action?: string;
  priority?: number;
}

export interface ComplianceReport {
  ok: boolean;
  numbers_in_draft?: string[];
  ungrounded?: string[];
  redacted_draft?: string;
}

export interface DraftRecord {
  counter_id: string;
  module_id: string;
  message: string;
  compliance: ComplianceReport;
}

/** Lifecycle of a persisted draft — mirrors `outreach_drafts.status`. */
export type DraftStatus = 'draft' | 'approved' | 'sent' | 'rejected';

/**
 * A draft as it sits in the counter record: the row shape returned by
 * `GET /outreach/{session_id}`. SQLite hands the compliance report back as a
 * raw JSON string, and `status` is what the Area Partner Manager's approval
 * actually moves — the SSE `draft` event carries neither, so the drawer
 * resolves the row by `counter_id` before it can edit or approve anything.
 */
export interface OutreachDraftRow {
  id: string;
  session_id: string;
  counter_id: string;
  module_id: string;
  channel: string;
  message: string;
  score: number | null;
  rationale_json: string | null;
  compliance_json: string | null;
  status: DraftStatus;
  created_at: string;
}

/** Payload behind the Counter 360 drawer. */
export interface CounterDetail {
  counter: Counter;
  source: string;
  transactions: Transaction[];
  modules: CounterModule[];
  field_notes: FieldNote[];
}

export type TraceEventName =
  | 'plan'
  | 'router'
  | 'tool_call'
  | 'tool_result'
  | 'critic'
  | 'synth'
  | 'candidate'
  | 'draft'
  | 'token'
  | 'final'
  | 'error'
  | 'info';

export interface TraceEvent {
  event: TraceEventName;
  ts: string;
  data: Record<string, unknown>;
  llm_route?: string | null;
  latency_ms?: number | null;
}

export interface SessionRow {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}
