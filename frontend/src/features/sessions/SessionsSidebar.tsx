import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { relTime, truncate } from '@/lib/format';
import { useUi } from '@/store/uiStore';
import type { SessionRow } from '@/lib/types';
import { Plus, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/cn';

export function SessionsSidebar() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const sessionId = useUi((s) => s.sessionId);
  const setSessionId = useUi((s) => s.setSessionId);
  const reset = useUi((s) => s.resetForNewQuery);

  async function refresh() {
    try {
      const rows = await api.listSessions();
      setSessions(rows);
    } catch {/* ignore */}
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 8000);
    return () => clearInterval(t);
  }, []);

  function newChat() {
    setSessionId(null);
    reset();
  }

  // Group by recency bucket
  const today: SessionRow[] = [];
  const earlier: SessionRow[] = [];
  const now = Date.now();
  for (const s of sessions) {
    const t = new Date(s.updated_at).getTime();
    if (now - t < 24 * 3600 * 1000) today.push(s);
    else earlier.push(s);
  }

  return (
    <div className="h-full flex flex-col bg-bg-soft/40">
      <div className="p-3 border-b border-border">
        <button onClick={newChat} className="btn-outline w-full justify-start text-sm">
          <Plus size={14} />
          New conversation
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-3 text-sm">
        {today.length > 0 && (
          <Group title="Today" rows={today} current={sessionId} onPick={setSessionId} />
        )}
        {earlier.length > 0 && (
          <Group title="Earlier" rows={earlier} current={sessionId} onPick={setSessionId} />
        )}
        {sessions.length === 0 && (
          <div className="px-2 py-6 text-center text-text-dim text-xs">
            No sessions yet. Start by asking a question.
          </div>
        )}
      </div>
      <div className="px-3 py-2 border-t border-border text-[11px] text-text-dim">
        v0.1 · Rohan · Mumbai West
      </div>
    </div>
  );
}

function Group({
  title,
  rows,
  current,
  onPick,
}: {
  title: string;
  rows: SessionRow[];
  current: string | null;
  onPick: (id: string) => void;
}) {
  return (
    <div>
      <div className="px-2 pb-1 eyebrow">{title}</div>
      <ul className="space-y-1">
        {rows.map((s) => (
          <li key={s.id}>
            <button
              onClick={() => onPick(s.id)}
              className={cn(
                'w-full text-left rounded-md px-2 py-1.5 flex items-start gap-2 transition-colors',
                current === s.id ? 'bg-accent/15 border border-accent-soft/40' : 'hover:bg-bg-soft',
              )}
            >
              <MessageSquare size={13} className="mt-0.5 text-text-muted" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-text">{truncate(s.title || 'Untitled', 38)}</div>
                <div className="text-[10px] text-text-dim">{relTime(s.updated_at)}</div>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
