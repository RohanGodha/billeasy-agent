import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { X, BookOpen, Search, Send, FileText, Sparkles, Loader2 } from 'lucide-react';

type Answer = Awaited<ReturnType<typeof api.knowledgeAsk>>;
type Sources = Awaited<ReturnType<typeof api.knowledgeSources>>;

export function KnowledgeModal({ onClose }: { onClose: () => void }) {
  const [meta, setMeta] = useState<Sources | null>(null);
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.knowledgeSources().then(setMeta).catch(() => null);
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function ask(q?: string) {
    const question = (q ?? query).trim();
    if (!question || loading) return;
    setQuery(question);
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await api.knowledgeAsk(question));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Please retry.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm animate-fade-in z-50" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-start justify-center p-3 sm:p-6 overflow-y-auto pointer-events-none">
        <div className="pointer-events-auto w-full max-w-2xl mt-6 sm:mt-12 card shadow-pop animate-slide-up flex flex-col max-h-[88vh]">
          {/* Header */}
          <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-md bg-accent/15 border border-accent-soft/40 flex items-center justify-center">
                <BookOpen size={14} className="text-accent-glow" />
              </div>
              <div>
                <div className="text-sm font-semibold">Payments Knowledge Base</div>
                <div className="text-[11px] text-text-dim">Payments compliance · Counter performance methodology · Field ops FAQs</div>
              </div>
            </div>
            <button onClick={onClose} className="icon-btn" title="Close"><X size={16} /></button>
          </div>

          {/* Search */}
          <div className="shrink-0 px-4 pt-3">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-dim" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && ask()}
                placeholder="Ask about GST e-invoicing, T+1 settlement, MDR, NCMC, merchant KYC…"
                className="input pl-9 pr-24"
              />
              <button
                onClick={() => ask()}
                disabled={loading || !query.trim()}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 btn-primary text-xs px-3 py-1"
              >
                {loading ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                Ask
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
            {!answer && !loading && !error && (
              <>
                {meta?.suggestions && (
                  <div>
                    <div className="eyebrow mb-2">Try asking</div>
                    <div className="flex flex-wrap gap-1.5">
                      {meta.suggestions.map((sug, i) => (
                        <button
                          key={i}
                          onClick={() => ask(sug)}
                          className="text-left text-[12px] rounded-full border border-border bg-bg-soft hover:border-accent/50 hover:bg-bg-card transition-colors px-3 py-1.5"
                        >
                          {sug}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {meta?.sources && (
                  <div>
                    <div className="eyebrow mb-2">Knowledge sources</div>
                    <div className="grid gap-2">
                      {meta.sources.map((s) => (
                        <div key={s.source} className="card p-3">
                          <div className="flex items-center gap-2 text-[12px] font-medium">
                            <FileText size={12} className="text-accent-glow" /> {s.source}
                          </div>
                          {s.sections.length > 0 && (
                            <div className="mt-1 text-[11px] text-text-dim leading-relaxed">
                              {s.sections.slice(0, 6).join(' · ')}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {loading && (
              <div className="flex items-center gap-2 text-sm text-text-muted py-6 justify-center">
                <Loader2 size={16} className="animate-spin" /> Searching the knowledge base…
              </div>
            )}

            {error && (
              <div className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</div>
            )}

            {answer && (
              <div className="animate-fade-in space-y-3">
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  <Sparkles size={12} className="text-accent-glow" />
                  <span>Answer</span>
                  {answer.llm_route && (
                    <span className="badge-accent text-[10px]">{answer.llm_route === 'documents' ? 'from documents' : answer.llm_route}</span>
                  )}
                </div>
                <div className="card p-4 text-sm leading-relaxed text-text whitespace-pre-wrap">{answer.answer}</div>
                {answer.sources.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[11px] text-text-dim">Sources:</span>
                    {answer.sources.map((s) => <span key={s} className="badge text-[10px]">{s}</span>)}
                  </div>
                )}
                <button onClick={() => { setAnswer(null); setQuery(''); inputRef.current?.focus(); }} className="btn-outline text-xs">
                  Ask another question
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
