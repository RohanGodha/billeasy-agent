import type { ScoreBreakdown } from '@/lib/types';
import { cn } from '@/lib/cn';

export function ScoreBreakdownChart({ features }: { features: ScoreBreakdown[] }) {
  const sliced = (features || []).slice(0, 5);
  if (sliced.length === 0)
    return (
      <p className="text-xs text-text-dim">No feature contributions returned.</p>
    );
  const maxAbs = Math.max(...sliced.map((f) => Math.abs(Number(f.contribution) || 0))) || 1;
  return (
    <div className="space-y-2">
      {sliced.map((f, i) => {
        const contribution = Number(f.contribution) || 0;
        const widthPct = Math.min(100, (Math.abs(contribution) / maxAbs) * 100);
        const isPos = f.direction === 'positive';
        const isNeg = f.direction === 'negative';
        return (
          <div key={f.feature || i} className="text-[12px]">
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-text">{prettyFeature(f.feature)}</span>
              <span
                className={cn(
                  'font-mono text-[11px]',
                  isPos ? 'text-positive' : isNeg ? 'text-danger' : 'text-text-muted',
                )}
              >
                {contribution >= 0 ? '+' : ''}
                {contribution.toFixed(2)}
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-bg-soft overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  isPos ? 'bg-positive/70' : isNeg ? 'bg-danger/70' : 'bg-text-dim/40',
                )}
                style={{ width: `${widthPct}%` }}
              />
            </div>
            {f.rationale && (
              <div className="text-[11px] text-text-dim mt-0.5">{f.rationale}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function prettyFeature(s?: string): string {
  if (!s) return '—';
  return s
    .replace(/_/g, ' ')
    .replace(/(^|\s)([a-z])/g, (_, p, c) => p + c.toUpperCase());
}
