/**
 * Binds the streamed draft on screen to the row the backend actually stores.
 *
 * The SSE `draft` event carries no row id and no status — those only exist once
 * the responder node writes the batch to `outreach_drafts` at the end of a run.
 * So the drawer resolves the row by `counter_id` out of
 * `GET /outreach/{session_id}` first; every edit and approval after that goes to
 * the server, and the row we hold is what the server last told us.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { OutreachDraftRow } from '@/lib/types';

/**
 * `loading`  — resolving the row
 * `ready`    — row on record, edits and approval will persist
 * `absent`   — session has no row for this counter yet (run still in flight)
 * `error`    — the lookup itself failed
 */
export type DraftSync = 'loading' | 'ready' | 'absent' | 'error';

export type DraftBusy = 'save' | 'approve' | null;

export interface OutreachDraftHandle {
  row: OutreachDraftRow | null;
  sync: DraftSync;
  busy: DraftBusy;
  /** Last failure, in the manager's words. Cleared when the next action starts. */
  error: string | null;
  approved: boolean;
  reload: () => void;
  clearError: () => void;
  /** PATCHes the message. Resolves `true` only if the server took the edit. */
  save: (message: string) => Promise<boolean>;
  /** Approves, then re-reads the row so the badge reflects stored status. */
  approve: () => Promise<boolean>;
}

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function useOutreachDraft(
  sessionId: string | null,
  counterId: string,
): OutreachDraftHandle {
  const [row, setRow] = useState<OutreachDraftRow | null>(null);
  const [sync, setSync] = useState<DraftSync>('loading');
  const [busy, setBusy] = useState<DraftBusy>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  /** Guards state writes after the drawer closes or the counter changes. */
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  /** Latest row for this counter — a session re-run appends, so take the last. */
  const fetchRow = useCallback(async (): Promise<OutreachDraftRow | null> => {
    if (!sessionId) return null;
    const { drafts } = await api.listDrafts(sessionId);
    const mine = drafts.filter((d) => d.counter_id === counterId);
    return mine.length ? mine[mine.length - 1] : null;
  }, [sessionId, counterId]);

  useEffect(() => {
    let cancelled = false;
    if (!sessionId) {
      setRow(null);
      setSync('absent');
      return;
    }
    setSync('loading');
    setError(null);
    fetchRow()
      .then((found) => {
        if (cancelled || !live.current) return;
        setRow(found);
        setSync(found ? 'ready' : 'absent');
      })
      .catch((e: unknown) => {
        if (cancelled || !live.current) return;
        setRow(null);
        setSync('error');
        setError(`Could not read this draft off the counter record. ${msg(e)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [fetchRow, sessionId, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const clearError = useCallback(() => setError(null), []);

  const save = useCallback(
    async (message: string): Promise<boolean> => {
      if (!row) {
        setError('This draft is not on the counter record yet, so the edit cannot be saved.');
        return false;
      }
      setBusy('save');
      setError(null);
      try {
        await api.updateDraft(row.id, message);
        if (live.current) setRow({ ...row, message });
        return true;
      } catch (e: unknown) {
        if (live.current) setError(`Edit not saved. ${msg(e)}`);
        return false;
      } finally {
        if (live.current) setBusy(null);
      }
    },
    [row],
  );

  const approve = useCallback(async (): Promise<boolean> => {
    if (!row) {
      setError('This draft is not on the counter record yet, so it cannot be approved.');
      return false;
    }
    setBusy('approve');
    setError(null);
    try {
      await api.approveDrafts([row.id]);
      // The approve endpoint echoes the request size, not the rows it touched,
      // so read the row back rather than assume the status moved.
      const confirmed = await fetchRow();
      if (live.current && confirmed) setRow(confirmed);
      if (confirmed?.status === 'approved') return true;
      if (live.current) {
        setError('The server did not record this draft as approved. Try again.');
      }
      return false;
    } catch (e: unknown) {
      if (live.current) setError(`Approval failed. ${msg(e)}`);
      return false;
    } finally {
      if (live.current) setBusy(null);
    }
  }, [row, fetchRow]);

  return {
    row,
    sync,
    busy,
    error,
    approved: row?.status === 'approved' || row?.status === 'sent',
    reload,
    clearError,
    save,
    approve,
  };
}
