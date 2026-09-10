import { useState } from 'react';
import { api, setToken } from '@/lib/api';
import { Lock, ShieldCheck } from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';
import { ThemeToggle } from '@/components/ThemeToggle';

export function Login({ onAuth }: { onAuth: () => void }) {
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { theme, toggle } = useTheme();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.verifyPassword(password);
      setToken(res.token);
      onAuth();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid password');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="fixed top-3 right-3">
        <ThemeToggle theme={theme} onToggle={toggle} />
      </div>
      <form
        onSubmit={onSubmit}
        className="card w-full max-w-sm p-6 sm:p-8 space-y-5 animate-fade-in"
        autoComplete="off"
      >
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-md bg-accent/15 border border-accent-soft/40 flex items-center justify-center text-accent-glow">
            <ShieldCheck size={18} />
          </div>
          <div>
            <h1 className="text-base font-semibold">Counter Copilot</h1>
            <p className="text-xs text-text-muted">Every counter, accounted for.</p>
          </div>
        </div>

        <div className="space-y-2">
          <label htmlFor="pwd" className="text-xs text-text-muted">
            Access password
          </label>
          <div className="relative">
            <Lock
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-dim pointer-events-none"
            />
            <input
              id="pwd"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input pl-8"
              placeholder="Enter shared password"
              autoFocus
              required
            />
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
        </div>

        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting ? 'Verifying…' : 'Sign in'}
        </button>

        <p className="text-[11px] text-text-dim leading-relaxed">
          Single-tenant demo build. The password is set per-deployment and shared with
          authorised reviewers only.
        </p>
      </form>
    </div>
  );
}
