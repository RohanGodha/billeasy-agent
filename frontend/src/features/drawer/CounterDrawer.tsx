import { useEffect, useState } from 'react';
import { useUi } from '@/store/uiStore';
import { api } from '@/lib/api';
import { inr, maskPhone, pct, relTime, truncate, cap } from '@/lib/format';
import { cn } from '@/lib/cn';
import { X, Phone, MapPin, Briefcase, Calendar, AlertTriangle, CheckCircle2, Sparkles } from 'lucide-react';
import { WhatsAppPreview } from './WhatsAppPreview';
import { ScoreBreakdownChart } from './ScoreBreakdownChart';
import { D3Loader } from '@/features/trace/D3Loader';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import type { CandidateRecord, Counter, CounterDetail } from '@/lib/types';

export function CounterDrawer({ counterId }: { counterId: string }) {
  const setSelectedCounterId = useUi((s) => s.setSelectedCounterId);
  const close = () => setSelectedCounterId(null);
  const candidate = useUi((s) =>
    s.candidates.find((c) => c.counter_id === counterId) || null,
  );
  const draft = useUi((s) =>
    s.drafts.find((d) => d.counter_id === counterId) || null,
  );

  const [data, setData] = useState<CounterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setErr(null);
    api
      .getCounter(counterId)
      .then(setData)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [counterId]);

  return (
    <>
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm animate-fade-in z-40"
        onClick={close}
      />
      <aside className="fixed right-0 top-0 h-screen w-full sm:w-[560px] lg:w-[680px] max-w-[100vw] bg-bg border-l border-border shadow-pop z-50 animate-slide-in-right overflow-hidden flex flex-col">
        <header className="shrink-0 h-12 px-4 flex items-center justify-between border-b border-border bg-bg-soft">
          <div className="flex items-center gap-2">
            <Sparkles size={14} className="text-accent-glow" />
            <span className="text-sm font-semibold">Counter 360</span>
          </div>
          <button onClick={close} className="icon-btn" title="Close">
            <X size={16} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
          <ErrorBoundary label="Counter details">
          {loading && <Skeleton />}
          {err && (
            <div className="text-sm text-danger flex items-center gap-2">
              <AlertTriangle size={14} /> {err}
            </div>
          )}
          {data && (
            <>
              <ProfileBlock counter={data.counter} source={data.source} candidate={candidate} />
              {candidate && (
                <Section title="Score Breakdown" subtitle="Top signals driving this counter's rank">
                  <ErrorBoundary compact label="Score breakdown">
                    <ScoreBreakdownChart features={candidate.top_features} />
                  </ErrorBoundary>
                  <div className="mt-3 text-xs text-text-muted leading-relaxed">
                    {candidate.rationale}
                  </div>
                </Section>
              )}
              {draft && (
                <Section
                  title="WhatsApp Draft"
                  subtitle={draft.compliance?.ok
                    ? 'All numbers grounded · ready to send'
                    : `${(draft.compliance?.ungrounded || []).length} ungrounded number(s) stripped`}
                  badge={
                    draft.compliance?.ok ? (
                      <span className="badge-pos">
                        <CheckCircle2 size={11} /> Compliance OK
                      </span>
                    ) : (
                      <span className="badge-warn">
                        <AlertTriangle size={11} /> Redacted
                      </span>
                    )
                  }
                >
                  <ErrorBoundary compact label="WhatsApp draft">
                    <WhatsAppPreview counter={data.counter} draft={draft} />
                  </ErrorBoundary>
                </Section>
              )}
              <Section title="Live Modules" subtitle={`${data.modules.length} active`}>
                <ul className="space-y-1.5 text-sm">
                  {data.modules.map((m) => (
                    <li key={m.module_id} className="flex items-center justify-between rounded-md bg-bg-card border border-border px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Briefcase size={12} className="text-text-muted" />
                        <span>{m.name}</span>
                      </div>
                      <span className="badge text-[10px]">{m.category}</span>
                    </li>
                  ))}
                  {data.modules.length === 0 && (
                    <li className="text-text-dim text-xs">No Billeasy modules live on this counter.</li>
                  )}
                </ul>
              </Section>
              <Section title="Recent Transactions" subtitle={`Last 6 months · ${data.transactions.length} txns`}>
                <ul className="space-y-1 text-[12px]">
                  {data.transactions.slice(0, 8).map((t) => (
                    <li key={t.id} className="flex items-center justify-between rounded-md bg-bg-soft/60 px-3 py-1.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <Calendar size={10} className="text-text-dim" />
                        <span className="text-text-muted text-[11px]">{relTime(t.ts)}</span>
                        <span className="text-text truncate">{t.instrument || t.channel}</span>
                        <span className="badge text-[10px]">{t.category}</span>
                      </div>
                      <span className={cn('font-mono', t.amount > 0 ? 'text-positive' : 'text-danger')}>
                        {t.amount > 0 ? '+' : ''}
                        {inr(t.amount, { compact: true })}
                      </span>
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Field Notes" subtitle={`${data.field_notes.length} note(s) on file`}>
                <ul className="space-y-2 text-sm">
                  {data.field_notes.map((n) => (
                    <li key={n.id} className="rounded-md bg-bg-card border border-border p-3">
                      <div className="flex items-center gap-2 text-[11px] text-text-muted mb-1">
                        <span className="badge text-[10px]">{n.channel}</span>
                        <span>{relTime(n.ts)}</span>
                      </div>
                      <div className="text-text leading-relaxed">{n.summary}</div>
                    </li>
                  ))}
                  {data.field_notes.length === 0 && (
                    <li className="text-text-dim text-xs">No field visits or tickets logged.</li>
                  )}
                </ul>
              </Section>
            </>
          )}
          </ErrorBoundary>
        </div>
      </aside>
    </>
  );
}

function ProfileBlock({
  counter,
  source,
  candidate,
}: {
  counter: Counter;
  source: string;
  candidate: CandidateRecord | null;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold">{counter.name}</div>
          <div className="text-xs text-text-muted mt-0.5 flex items-center flex-wrap gap-x-3 gap-y-1.5">
            <span className="inline-flex items-center gap-1">
              <MapPin size={11} /> {counter.city}
            </span>
            <span className="inline-flex items-center gap-1">
              <Phone size={11} /> {maskPhone(counter.phone)}
            </span>
            <span className="badge text-[10px]">{cap(counter.tier)}</span>
            <span className="badge text-[10px]">{cap(counter.counter_type)}</span>
            <span className="badge text-[10px]">Data: {source}</span>
            {candidate?.leakage_band && candidate.leakage_band !== 'clear' && (
              <span
                className={
                  candidate.leakage_band === 'watch'
                    ? 'badge text-[10px]'
                    : 'badge-warn text-[10px]'
                }
                title="Share of the maximum revenue-leakage evidence visible for this counter"
              >
                Leakage {Math.round((candidate.leakage_risk ?? 0) * 100)}% ·{' '}
                {candidate.leakage_band}
              </span>
            )}
            {candidate?.escalate && candidate.leakage_band === 'clear' && (
              <span className="badge-warn text-[10px]">Escalate</span>
            )}
            {candidate?.sentiment && candidate.sentiment !== 'neutral' && (
              <span className={candidate.sentiment === 'negative' ? 'badge-neg text-[10px]' : 'badge-pos text-[10px]'}>
                {cap(candidate.sentiment)}
              </span>
            )}
          </div>
          <div className="text-[11px] text-text-dim mt-1.5">
            {counter.operator} · Settles {counter.settlement_cycle} · KYC {counter.kyc_status}
          </div>
        </div>
        {candidate && (
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wider text-text-dim">Composite</div>
            <div className="text-xl font-semibold text-accent-glow">
              {Math.round(candidate.composite_score * 100)}
            </div>
            <div className="text-[10px] text-text-dim">
              v {pct(candidate.value_score)} · p {pct(candidate.propensity_score)}
            </div>
          </div>
        )}
      </div>
      <div className="mt-3 grid grid-cols-2 xs:grid-cols-3 gap-2 text-xs">
        <Stat label="Monthly TPV" value={inr(counter.monthly_tpv, { compact: true })} />
        <Stat label="Avg daily txns" value={counter.avg_daily_txns != null ? Math.round(counter.avg_daily_txns) : '—'} />
        <Stat label="Digital share" value={pct(counter.digital_share)} />
        <Stat label="Pending settlement" value={inr(counter.pending_settlement, { compact: true })} />
        <Stat label="Onboarded" value={truncate(counter.onboarded_date, 10)} />
      </div>
      {candidate?.next_action && (
        <div className="mt-3 flex items-center justify-between gap-2 rounded-md border border-accent-soft/40 bg-accent/10 px-3 py-2">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-text-dim">Recommended action</div>
            <div className="text-sm font-medium text-text">{candidate.next_action}</div>
          </div>
          {candidate.opportunity_value ? (
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wider text-text-dim">Est. opportunity</div>
              <div className="text-sm font-semibold text-positive">
                {inr(candidate.opportunity_value, { compact: true })}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md bg-bg-soft px-3 py-2 border border-border">
      <div className="text-[10px] uppercase tracking-wider text-text-dim">{label}</div>
      <div className="text-sm font-medium text-text mt-0.5">{value}</div>
    </div>
  );
}

function Section({
  title,
  subtitle,
  badge,
  children,
}: {
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-baseline gap-2">
          <h3 className="text-sm font-semibold">{title}</h3>
          {subtitle && <span className="text-[11px] text-text-dim">{subtitle}</span>}
        </div>
        {badge}
      </div>
      {children}
    </section>
  );
}

function Skeleton() {
  return (
    <div className="space-y-4">
      <div className="flex justify-center py-4">
        <D3Loader size={32} label="Loading Counter 360…" />
      </div>
      <div className="h-24 skeleton" />
      <div className="h-32 skeleton" />
      <div className="h-40 skeleton" />
    </div>
  );
}
