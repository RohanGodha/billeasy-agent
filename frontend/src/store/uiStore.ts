import { create } from 'zustand';
import type { CandidateRecord, DraftRecord, TraceEvent } from '@/lib/types';

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

interface UiState {
  sessionId: string | null;
  managerQuery: string;
  isStreaming: boolean;
  transcript: ChatTurn[];
  events: TraceEvent[];
  candidates: CandidateRecord[];
  drafts: DraftRecord[];
  summary: string;
  selectedCounterId: string | null;
  error: string | null;

  setSessionId(id: string | null): void;
  setManagerQuery(q: string): void;
  addTurn(role: 'user' | 'assistant', content: string): void;
  startStream(): void;
  pushEvent(ev: TraceEvent): void;
  pushCandidate(c: CandidateRecord): void;
  pushDraft(d: DraftRecord): void;
  setSummary(s: string): void;
  setSelectedCounterId(id: string | null): void;
  setError(e: string | null): void;
  finishStream(): void;
  resetForNewQuery(): void;
}

export const useUi = create<UiState>((set) => ({
  sessionId: null,
  managerQuery: '',
  isStreaming: false,
  transcript: [],
  events: [],
  candidates: [],
  drafts: [],
  summary: '',
  selectedCounterId: null,
  error: null,

  setSessionId: (id) => set({ sessionId: id }),
  setManagerQuery: (q) => set({ managerQuery: q }),
  addTurn: (role, content) => set((s) => ({ transcript: [...s.transcript, { role, content }] })),
  startStream: () =>
    set({
      isStreaming: true,
      events: [],
      candidates: [],
      drafts: [],
      summary: '',
      error: null,
    }),
  pushEvent: (ev) => set((s) => ({ events: [...s.events, ev] })),
  pushCandidate: (c) =>
    set((s) => {
      const idx = s.candidates.findIndex((x) => x.counter_id === c.counter_id);
      const next = [...s.candidates];
      if (idx >= 0) next[idx] = c;
      else next.push(c);
      // Mirror the backend's action-queue order: priority first, then leakage
      // severity, then commercial fit. Sorting on composite_score alone silently
      // discarded that ranking, so the panel could disagree with the summary the
      // agent had just written — the counter it told you to call first was not the
      // one at the top of the list.
      next.sort(
        (a, b) =>
          (a.priority ?? 3) - (b.priority ?? 3) ||
          (b.leakage_risk ?? 0) - (a.leakage_risk ?? 0) ||
          b.composite_score - a.composite_score,
      );
      return { candidates: next };
    }),
  pushDraft: (d) =>
    set((s) => {
      const idx = s.drafts.findIndex((x) => x.counter_id === d.counter_id);
      const next = [...s.drafts];
      if (idx >= 0) next[idx] = d;
      else next.push(d);
      return { drafts: next };
    }),
  setSummary: (text) => set({ summary: text }),
  setSelectedCounterId: (id) => set({ selectedCounterId: id }),
  setError: (e) => set({ error: e }),
  finishStream: () => set({ isStreaming: false }),
  resetForNewQuery: () =>
    set({
      transcript: [],
      events: [],
      candidates: [],
      drafts: [],
      summary: '',
      error: null,
      isStreaming: false,
    }),
}));
