import { useState, useRef, useEffect } from 'react';
import { useUi } from '@/store/uiStore';
import { useAgentStream } from '@/hooks/useAgentStream';
import { TracePanel } from '@/features/trace/TracePanel';
import { AgentFlowD3 } from '@/features/trace/AgentFlowD3';
import { D3Loader } from '@/features/trace/D3Loader';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ArrowUp, Sparkles, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Markdown } from '@/components/Markdown';

const QUICK_PROMPTS = [
  'Find ferry and bus counters in Mumbai leaking digital ticket revenue this month and draft WhatsApp nudges for the supervisors.',
  "Which retail outlets crossed the GST e-invoice threshold but aren't issuing compliant bills?",
  'Show anchor counters with settlement mismatches above 2% and recommend the right Billeasy module.',
];

export function ChatPane() {
  const ui = useUi();
  const { run } = useAgentStream();
  const [input, setInput] = useState('');
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    taRef.current?.focus();
  }, []);

  function submit(q?: string) {
    const query = (q ?? input).trim();
    if (!query || ui.isStreaming) return;
    setInput('');
    void run({ query, sessionId: ui.sessionId });
  }

  return (
    <div className="h-full flex flex-col">
      {/* Conversation / trace area */}
      <div className="flex-1 overflow-y-auto px-3 sm:px-5 lg:px-6 py-4 sm:py-6 space-y-5 sm:space-y-6">
        {/* Full conversation transcript */}
        {ui.transcript.map((turn, i) =>
          turn.role === 'user' ? (
            <div key={i} className="flex justify-end animate-fade-in">
              <div className="max-w-[85%] sm:max-w-[80%] rounded-2xl rounded-tr-sm bg-accent/15 border border-accent-soft/40 px-4 py-2.5 text-sm text-text whitespace-pre-wrap break-words">
                {turn.content}
              </div>
            </div>
          ) : (
            <AssistantBubble key={i} text={turn.content} />
          ),
        )}

        {/* Live D3 pipeline visual while the agent is reasoning */}
        {ui.isStreaming && ui.events.length > 0 && (
          <div className="rounded-2xl rounded-tl-sm bg-bg-card border border-border px-3 py-2 animate-fade-in">
            <div className="flex items-center gap-2 mb-1 px-1">
              <D3Loader size={20} />
              <span className="text-xs text-text-muted">Agent is working…</span>
            </div>
            <ErrorBoundary compact label="Pipeline view">
              <AgentFlowD3 />
            </ErrorBoundary>
          </div>
        )}

        {/* Trace panel — the current run's reasoning (events cleared each run) */}
        {ui.events.length > 0 && (
          <ErrorBoundary compact label="Trace">
            <TracePanel />
          </ErrorBoundary>
        )}

        {/* Live assistant preview while streaming (before the final turn is committed) */}
        {ui.isStreaming && ui.summary && <AssistantBubble text={ui.summary} />}

        {/* Initial thinking indicator (before any event arrives) */}
        {ui.isStreaming && ui.events.length === 0 && (
          <div className="animate-fade-in">
            <D3Loader size={24} label="Thinking…" />
          </div>
        )}

        {ui.error && (
          <div className="flex items-start gap-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            <AlertCircle size={14} className="mt-0.5" />
            <span>{ui.error}</span>
          </div>
        )}

        {/* Empty state */}
        {ui.transcript.length === 0 && !ui.isStreaming && (
          <EmptyState onPick={(q) => { setInput(q); submit(q); }} />
        )}
      </div>

      {/* Composer */}
      <div className="shrink-0 border-t border-border p-2.5 sm:p-3">
        <div className="rounded-xl border border-border bg-bg-card focus-within:border-accent/60 focus-within:shadow-glow transition-all">
          <textarea
            ref={taRef}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Ask Copilot to find leaking counters, score them, draft supervisor nudges…"
            className="w-full resize-none bg-transparent px-3 py-2.5 text-sm placeholder:text-text-dim focus:outline-none"
            disabled={ui.isStreaming}
          />
          <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-1">
            <div className="text-[11px] text-text-dim truncate">
              <span className="hidden sm:inline">Enter to send · Shift+Enter for newline</span>
              <span className="sm:hidden">Enter to send</span>
            </div>
            <button
              onClick={() => submit()}
              disabled={ui.isStreaming || input.trim() === ''}
              className={cn(
                'inline-flex items-center justify-center h-7 w-7 rounded-md transition-colors',
                ui.isStreaming || input.trim() === ''
                  ? 'bg-bg-soft text-text-dim cursor-not-allowed'
                  : 'bg-accent text-white hover:bg-accent-glow',
              )}
              aria-label="Send"
            >
              <ArrowUp size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function AssistantBubble({ text }: { text: string }) {
  return (
    <div className="flex animate-fade-in">
      <div className="max-w-[88%] space-y-2">
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <Sparkles size={12} className="text-accent-glow" />
          <span>Counter Copilot</span>
        </div>
        <div className="rounded-2xl rounded-tl-sm bg-bg-card border border-border px-4 py-3 text-sm leading-relaxed text-text">
          <Markdown text={text} />
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="max-w-2xl mx-auto pt-4 sm:pt-6 animate-fade-in">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center justify-center h-10 w-10 rounded-xl bg-accent/10 border border-accent-soft/30 text-accent-glow">
          <Sparkles size={18} />
        </div>
        <h2 className="text-base sm:text-lg font-semibold">{greeting()}, Rohan.</h2>
        <p className="text-sm text-text-muted px-2">
          Ask in plain language. I’ll query the network, score your counters, flag revenue
          leakage, and draft compliant WhatsApp nudges.
        </p>
      </div>
      <div className="mt-5 sm:mt-6 grid gap-2">
        <div className="eyebrow px-1">Try one of these</div>
        {QUICK_PROMPTS.map((q, i) => (
          <button
            key={i}
            onClick={() => onPick(q)}
            className="text-left text-sm rounded-lg border border-border bg-bg-card card-hover px-4 py-3"
          >
            <span className="text-text">{q}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}
