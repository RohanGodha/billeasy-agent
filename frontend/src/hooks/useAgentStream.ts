/**
 * Streams the agent's events from the backend SSE endpoint.
 * Uses `@microsoft/fetch-event-source` so we can send the auth header.
 *
 * Connection resilience: `fetchEventSource` reconnects on its own only if `onerror`
 * does not throw, and each reconnection re-POSTs the same body — which would re-run the
 * whole agent pipeline and duplicate drafts. So the library's automatic reconnection is
 * deliberately disabled (every `onerror` throws), and *we* decide when to retry:
 *
 *   - only before ANY server frame arrived (`delivered === 0`) — once the run has begun
 *     (e.g. a `plan` event), a reconnect would produce a second, competing run;
 *   - only on transport-level or 5xx/408/429 failures — a 4xx means the request itself
 *     is wrong and will never succeed;
 *   - at most a few times, with exponential backoff + jitter.
 */
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useCallback } from 'react';
import { API_BASE, getToken } from '@/lib/api';
import type {
  CandidateRecord,
  DraftRecord,
  TraceEvent,
  TraceEventName,
} from '@/lib/types';
import { useUi } from '@/store/uiStore';

interface RunArgs {
  query: string;
  sessionId?: string | null;
  /** Area Partner Manager the copilot is working for. */
  managerName?: string;
}

/** Loosely-typed SSE frame — the server sends one JSON object per event. */
type StreamPayload = Record<string, unknown>;

const MAX_ATTEMPTS = 4;
const BASE_BACKOFF_MS = 800;

class FatalStreamError extends Error {
  status: number;

  constructor(status: number) {
    super(`HTTP ${status}`);
    this.status = status;
    this.name = 'FatalStreamError';
  }
}

function str(v: unknown): string | undefined {
  return typeof v === 'string' && v !== '' ? v : undefined;
}

function backoffMs(attempt: number): number {
  const base = BASE_BACKOFF_MS * 2 ** (attempt - 1);
  return base + Math.round(base * 0.25 * Math.random());
}

function isRetryable(err: unknown, delivered: number): boolean {
  if (delivered > 0) return false; // the run already started; never fork a duplicate
  if (err instanceof FatalStreamError) {
    // 4xx (other than 408 timeouts) is a permanent rejection — do not hammer it.
    return err.status >= 500 || err.status === 408 || err.status === 429;
  }
  return true; // transport-level (DNS, refused, reset mid-handshake)
}

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => window.setTimeout(resolve, ms));

export function useAgentStream() {
  const ui = useUi();

  const run = useCallback(
    async (args: RunArgs) => {
      const token = getToken();
      if (!token) {
        ui.setError('Not authenticated. Please log in again.');
        return;
      }
      ui.setManagerQuery(args.query);
      ui.addTurn('user', args.query);
      ui.startStream();

      const runCtrl = new AbortController();
      let delivered = 0;

      const attempt = async (): Promise<void> => {
        const tryCtrl = new AbortController();
        const onRunAbort = () => tryCtrl.abort();
        runCtrl.signal.addEventListener('abort', onRunAbort);
        try {
          await fetchEventSource(`${API_BASE}/chat/stream`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Access-Token': token,
              Accept: 'text/event-stream',
            },
            body: JSON.stringify({
              session_id: args.sessionId ?? null,
              manager_query: args.query,
              manager_name: args.managerName ?? 'Rohan',
            }),
            signal: tryCtrl.signal,
            openWhenHidden: true,
            async onopen(response) {
              if (!response.ok) {
                throw new FatalStreamError(response.status);
              }
              const type = response.headers.get('content-type') ?? '';
              if (!type.startsWith('text/event-stream')) {
                throw new Error(`Expected text/event-stream, got: ${type}`);
              }
            },
            onmessage(msg) {
              delivered += 1;
              const eventName = (msg.event || 'token') as TraceEventName;
              let payload: StreamPayload = {};
              try {
                payload = msg.data ? (JSON.parse(msg.data) as StreamPayload) : {};
              } catch {
                payload = { data: msg.data };
              }
              const nested = payload.data as StreamPayload | undefined;
              const evt: TraceEvent = {
                event: eventName,
                ts: str(payload.ts) ?? new Date().toISOString(),
                data: nested && typeof nested === 'object' ? nested : payload,
                llm_route: str(payload.llm_route) ?? null,
                latency_ms: typeof payload.latency_ms === 'number' ? payload.latency_ms : null,
              };
              ui.pushEvent(evt);

              const d = evt.data as StreamPayload;
              if (eventName === 'info' && str(d.session_id)) {
                ui.setSessionId(str(d.session_id) ?? null);
              }
              if (eventName === 'candidate' && str(d.counter_id)) {
                ui.pushCandidate(d as unknown as CandidateRecord);
              }
              if (eventName === 'draft' && str(d.counter_id)) {
                ui.pushDraft({
                  counter_id: String(d.counter_id),
                  module_id: str(d.module_id) ?? '',
                  message: str(d.message) ?? '',
                  compliance: (d.compliance as DraftRecord['compliance']) ?? { ok: true },
                });
              }
              if (eventName === 'synth' && str(d.summary)) {
                ui.setSummary(str(d.summary) ?? '');
              }
              if (eventName === 'final') {
                const summary = str(d.summary);
                if (summary) ui.setSummary(summary);
                if (Array.isArray(d.candidates)) {
                  (d.candidates as CandidateRecord[]).forEach((c) => ui.pushCandidate(c));
                }
                if (Array.isArray(d.drafts)) {
                  (d.drafts as DraftRecord[]).forEach((dr) => ui.pushDraft(dr));
                }
                if (summary) ui.addTurn('assistant', summary);
                ui.finishStream();
              }
              if (eventName === 'error') {
                ui.setError(str(d.error) ?? 'Unknown error');
                ui.finishStream();
              }
            },
            onerror(err: unknown) {
              // Always throw: suppresses the library's internal reconnect (which would
              // blindly re-run the agent pipeline server-side). We retry explicitly.
              throw err;
            },
          });
        } finally {
          runCtrl.signal.removeEventListener('abort', onRunAbort);
        }
      };

      try {
        for (let n = 1; n <= MAX_ATTEMPTS; n += 1) {
          try {
            await attempt();
            return () => runCtrl.abort();
          } catch (err: unknown) {
            if (runCtrl.signal.aborted) {
              return () => runCtrl.abort();
            }
            if (isRetryable(err, delivered) && n < MAX_ATTEMPTS) {
              await sleep(backoffMs(n));
              continue;
            }
            if (err instanceof FatalStreamError && err.status === 401) {
              ui.setError('Session expired. Please log in again.');
            } else if (!runCtrl.signal.aborted) {
              ui.setError(err instanceof Error ? err.message : String(err));
            }
            ui.finishStream();
            return () => runCtrl.abort();
          }
        }
      } finally {
        // A clean `final` already finished the stream; a dropped run must never leave
        // the UI spinning.
        ui.finishStream();
      }

      return () => runCtrl.abort();
    },
    [ui],
  );

  return { run };
}