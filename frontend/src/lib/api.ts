/**
 * Thin REST client. The shared password token is read from localStorage and
 * forwarded as `X-Access-Token` on every request. For the SSE stream we have
 * a separate hook that uses `@microsoft/fetch-event-source`.
 */
import type {
  Counter,
  CounterDetail,
  CounterModule,
  FieldNote,
  OutreachDraftRow,
  SessionRow,
  TraceEvent,
  Transaction,
} from './types';

const RAW_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const API_BASE = RAW_BASE.replace(/\/$/, '');

const TOKEN_KEY = 'counter-copilot.token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = getToken() ?? '';
  return { 'X-Access-Token': token, ...(extra || {}) };
}

async function jfetch<T>(path: string, init?: RequestInit, timeoutMs = 30000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
        ...(init?.headers || {}),
      },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status} ${res.statusText}: ${text || path}`);
    }
    return res.json() as Promise<T>;
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') {
      throw new Error(`Request timed out. The server may be waking up — please retry.`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Wire shape of `GET /counters/:id`. The enrichment lists are read defensively
 * so the drawer keeps rendering whichever key the API ships them under.
 */
interface CounterDetailPayload {
  counter: Counter;
  source: string;
  transactions?: Transaction[];
  modules?: CounterModule[];
  holdings?: CounterModule[];
  field_notes?: FieldNote[];
  interactions?: FieldNote[];
}

export const api = {
  async verifyPassword(password: string) {
    const res = await fetch(`${API_BASE}/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) throw new Error('Invalid password');
    return res.json() as Promise<{ ok: boolean; token: string }>;
  },
  status: () => jfetch<{
    datasource_active: string;
    datasource_healthy: boolean;
    llm_providers: Record<string, boolean>;
  }>('/status'),
  listSessions: () => jfetch<SessionRow[]>('/sessions'),
  createSession: (title?: string) =>
    jfetch<SessionRow>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  getTrace: (sessionId: string) =>
    jfetch<{
      events: TraceEvent[];
      messages: { role: string; content: string }[];
      drafts: OutreachDraftRow[];
    }>(`/trace/${sessionId}`),
  async getCounter(counterId: string): Promise<CounterDetail> {
    const raw = await jfetch<CounterDetailPayload>(`/counters/${counterId}`);
    return {
      counter: raw.counter,
      source: raw.source,
      transactions: raw.transactions ?? [],
      modules: raw.modules ?? raw.holdings ?? [],
      field_notes: raw.field_notes ?? raw.interactions ?? [],
    };
  },
  /** Every draft persisted against a session, oldest first. */
  listDrafts: (sessionId: string) =>
    jfetch<{ drafts: OutreachDraftRow[] }>(`/outreach/${encodeURIComponent(sessionId)}`),
  /** Persist the manager's edit to a draft. 404s if the draft is not on record. */
  updateDraft: (draftId: string, message: string) =>
    jfetch<{ ok: boolean; id: string }>(`/outreach/${encodeURIComponent(draftId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ message }),
    }),
  /**
   * Mark drafts approved. The count returned is the size of the request, not
   * the number of rows the update touched, so callers that need the truth
   * re-read the row with `listDrafts` afterwards.
   */
  approveDrafts: (draftIds: string[]) =>
    jfetch<{ approved: number }>('/outreach/approve', {
      method: 'POST',
      body: JSON.stringify({ draft_ids: draftIds }),
    }),
  listTools: () =>
    jfetch<{
      tools: { name: string; description: string }[];
      count: number;
    }>('/tools'),
  capabilities: () => jfetch<{
    domain: { name: string; persona: string; scope: string; out_of_scope: string };
    capabilities: { title: string; desc: string }[];
    modules: { id: string; name: string; category: string }[];
    example_prompts: string[];
    faq_count: number;
    status: { datasource: string; llm: string; rag: string };
  }>('/meta/capabilities'),
  faqs: () => jfetch<{ count: number; categories: Record<string, { q: string; a: string }[]> }>('/meta/faqs'),
  knowledgeSources: () => jfetch<{
    sources: { source: string; sections: string[] }[];
    suggestions: string[];
  }>('/knowledge/sources'),
  knowledgeAsk: (query: string) =>
    jfetch<{
      answer: string;
      sources: string[];
      excerpts: { source: string; title: string; score: number }[];
      llm_route: string | null;
      latency_ms: number;
    }>('/knowledge/ask', { method: 'POST', body: JSON.stringify({ query }) }, 60000),
};
