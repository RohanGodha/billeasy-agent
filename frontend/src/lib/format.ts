/** INR-friendly formatters. */

export function inr(value: number | null | undefined, opts: { compact?: boolean } = {}): string {
  if (value == null || Number.isNaN(value)) return '—';
  if (opts.compact) {
    const abs = Math.abs(value);
    if (abs >= 10_000_000) return `₹${(value / 10_000_000).toFixed(2)} Cr`;
    if (abs >= 100_000) return `₹${(value / 100_000).toFixed(2)} L`;
    if (abs >= 1_000) return `₹${(value / 1_000).toFixed(1)}k`;
  }
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value);
}

export function pct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(0)}%`;
}

export function relTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86_400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86_400)}d ago`;
}

export function truncate(s: string, n = 80): string {
  if (!s) return '';
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

export function maskPhone(phone?: string | null): string {
  if (!phone) return '—';
  return phone.replace(/(\d{2,3})-?(\d+)-(\d{2,3})$/, '$1-•••••-$3');
}

export function cap(s?: string | null): string {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function titleCase(s?: string | null): string {
  if (!s) return '';
  return s
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
