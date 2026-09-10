import { useUi } from '@/store/uiStore';
import { inr, pct, truncate } from '@/lib/format';
import { cn } from '@/lib/cn';
import { MapPin, ShoppingBag, Zap, Users, AlertTriangle, TrendingUp, ArrowRight } from 'lucide-react';

/** Leakage severity as a whole percentage, for badge copy. */
const leakPct = (risk?: number) => Math.round((risk ?? 0) * 100);

const TIER_LABEL: Record<string, string> = {
  nano: 'Nano',
  standard: 'Standard',
  flagship: 'Flagship',
  anchor: 'Anchor',
};

export function CandidatesPanel() {
  const candidates = useUi((s) => s.candidates);
  const setSelected = useUi((s) => s.setSelectedCounterId);
  const isStreaming = useUi((s) => s.isStreaming);

  return (
    <div className="h-full flex flex-col bg-bg-soft/40">
      <div className="panel-head">
        <div className="flex items-center gap-2">
          <Users size={14} className="text-accent-glow" />
          <span className="text-sm font-semibold">Candidates</span>
          <span className="text-[11px] text-text-dim">
            ({candidates.length}{isStreaming ? ' so far' : ''})
          </span>
        </div>
        {candidates.length > 0 && (
          <span className="hidden xl:inline text-[10px] text-text-dim">Sorted by composite score</span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {candidates.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center px-6">
            <div className="h-10 w-10 rounded-xl bg-bg-card border border-border flex items-center justify-center text-text-dim">
              <Users size={16} />
            </div>
            <p className="mt-3 text-sm text-text-muted">No counters shortlisted yet.</p>
            <p className="text-[11px] text-text-dim">
              {isStreaming
                ? 'Agent is scoring the network…'
                : 'Send a question to begin.'}
            </p>
          </div>
        )}

        {candidates.map((c) => (
          <button
            key={c.counter_id}
            onClick={() => setSelected(c.counter_id)}
            className="w-full text-left card p-3 hover:border-accent/50 transition-colors animate-fade-in"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium text-sm truncate">{c.name}</div>
                <div className="text-[11px] text-text-muted flex items-center gap-2 mt-0.5">
                  <span className="inline-flex items-center gap-1">
                    <MapPin size={10} />
                    {c.city || '—'}
                  </span>
                  <span className="badge text-[10px]">{TIER_LABEL[c.tier] || c.tier}</span>
                </div>
              </div>
              <ScoreRing score={c.composite_score} />
            </div>

            <div className="mt-2 flex items-center gap-2 text-[11px] flex-wrap">
              <ShoppingBag size={11} className="text-accent-glow" />
              <span className="text-text">{c.recommended_module_name}</span>
              {c.leakage_band === 'elevated' || c.leakage_band === 'severe' ? (
                <span
                  className="badge-warn"
                  title={`Revenue leakage at ${leakPct(c.leakage_risk)}% of the maximum evidence we can see — call the supervisor`}
                >
                  <AlertTriangle size={10} /> Leakage {leakPct(c.leakage_risk)}%
                </span>
              ) : c.escalate ? (
                <span className="badge-warn" title="Unresolved issue on file in the field notes">
                  <AlertTriangle size={10} /> Escalate
                </span>
              ) : c.leakage_band === 'watch' ? (
                <span
                  className="badge text-[10px]"
                  title={`Some leakage signal (${leakPct(c.leakage_risk)}%) — worth watching, not yet a call`}
                >
                  Watch {leakPct(c.leakage_risk)}%
                </span>
              ) : null}
              {c.sentiment === 'positive' && <span className="badge-pos">Positive</span>}
            </div>

            {c.top_features?.[0] && (
              <div className="mt-2 text-[11px] text-text-muted flex items-start gap-1">
                <Zap size={10} className="mt-0.5 text-accent-glow" />
                <span>{truncate(c.top_features[0].rationale, 88)}</span>
              </div>
            )}

            {(c.opportunity_value || c.next_action) && (
              <div className="mt-2 flex items-center justify-between gap-2 rounded-md bg-bg-soft/70 border border-border px-2 py-1.5">
                {c.opportunity_value ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-positive">
                    <TrendingUp size={11} />
                    {inr(c.opportunity_value, { compact: true })}
                    <span className="text-text-dim font-normal">opp.</span>
                  </span>
                ) : <span />}
                {c.next_action && (
                  <span className={cn(
                    'inline-flex items-center gap-1 text-[10px] font-medium',
                    c.priority === 1 ? 'text-warning' : 'text-text-muted',
                  )}>
                    <ArrowRight size={10} />
                    {c.next_action}
                  </span>
                )}
              </div>
            )}

            <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
              <KV k="Monthly TPV" v={inr(c.monthly_tpv, { compact: true })} />
              <KV k="Value" v={pct(c.value_score)} />
              <KV k="Propensity" v={pct(c.propensity_score)} />
              <KV k="Citations" v={c.citations?.length || 0} />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between">
      <span className="text-text-dim">{k}</span>
      <span className="text-text">{v}</span>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const pctNum = Math.round(score * 100);
  const tone =
    pctNum >= 75 ? 'text-positive' : pctNum >= 55 ? 'text-accent-glow' : 'text-warning';
  return (
    <div
      className={cn(
        'h-9 w-9 rounded-full border flex items-center justify-center text-[11px] font-semibold',
        tone,
        pctNum >= 75
          ? 'border-positive/40 bg-positive/10'
          : pctNum >= 55
          ? 'border-accent-soft/50 bg-accent/10'
          : 'border-warning/40 bg-warning/10',
      )}
    >
      {pctNum}
    </div>
  );
}


