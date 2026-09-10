import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import {
  X, Sparkles, Boxes, MessageSquareText, HelpCircle, Search,
  Database, Cpu, Layers, Send, Wand2,
} from 'lucide-react';

type Caps = Awaited<ReturnType<typeof api.capabilities>>;
type Faqs = Awaited<ReturnType<typeof api.faqs>>;

type Tab = 'overview' | 'faqs';

export function GuidePanel({
  onClose,
  onRunPrompt,
}: {
  onClose: () => void;
  onRunPrompt: (q: string) => void;
}) {
  const [caps, setCaps] = useState<Caps | null>(null);
  const [faqs, setFaqs] = useState<Faqs | null>(null);
  const [tab, setTab] = useState<Tab>('overview');
  const [query, setQuery] = useState('');

  useEffect(() => {
    api.capabilities().then(setCaps).catch(() => null);
    api.faqs().then(setFaqs).catch(() => null);
  }, []);

  const filteredFaqs = useMemo(() => {
    if (!faqs) return {} as Record<string, { q: string; a: string }[]>;
    if (!query.trim()) return faqs.categories;
    const q = query.toLowerCase();
    const out: Record<string, { q: string; a: string }[]> = {};
    for (const [cat, items] of Object.entries(faqs.categories)) {
      const hit = items.filter((i) => i.q.toLowerCase().includes(q) || i.a.toLowerCase().includes(q));
      if (hit.length) out[cat] = hit;
    }
    return out;
  }, [faqs, query]);

  return (
    <>
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm animate-fade-in z-40" onClick={onClose} />
      <aside className="fixed right-0 top-0 h-screen w-full sm:w-[560px] lg:w-[620px] max-w-[100vw] bg-bg border-l border-border shadow-pop z-50 animate-slide-in-right overflow-hidden flex flex-col">
        <header className="shrink-0 h-12 px-4 flex items-center justify-between border-b border-border bg-bg-soft">
          <div className="flex items-center gap-2">
            <Wand2 size={15} className="text-accent-glow" />
            <span className="text-sm font-semibold">What Counter Copilot Can Do</span>
          </div>
          <button onClick={onClose} className="icon-btn" title="Close"><X size={16} /></button>
        </header>

        {/* Status strip */}
        {caps && (
          <div className="px-4 py-2.5 border-b border-border grid grid-cols-3 gap-2">
            <Stat icon={<Cpu size={12} />} label="LLM" value={caps.status.llm} />
            <Stat icon={<Database size={12} />} label="Data" value={caps.status.datasource} />
            <Stat icon={<Layers size={12} />} label="RAG" value={caps.status.rag} />
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-border text-sm">
          <TabBtn active={tab === 'overview'} onClick={() => setTab('overview')} icon={<Sparkles size={13} />}>
            Overview
          </TabBtn>
          <TabBtn active={tab === 'faqs'} onClick={() => setTab('faqs')} icon={<HelpCircle size={13} />}>
            FAQs {caps ? `(${caps.faq_count})` : ''}
          </TabBtn>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {tab === 'overview' && caps && (
            <>
              <section>
                <Heading icon={<Sparkles size={13} />}>Domain</Heading>
                <div className="card p-3 text-[13px] text-text">
                  <div className="font-medium">{caps.domain.name}</div>
                  <div className="text-text-muted mt-1">{caps.domain.scope}</div>
                  <div className="text-text-dim text-[11px] mt-2">
                    <span className="text-text-muted">Out of scope:</span> {caps.domain.out_of_scope}
                  </div>
                </div>
              </section>

              <section>
                <Heading icon={<Sparkles size={13} />}>Capabilities</Heading>
                <div className="grid grid-cols-1 xs:grid-cols-2 gap-2">
                  {caps.capabilities.map((c) => (
                    <div key={c.title} className="card p-2.5">
                      <div className="text-[12px] font-medium text-text">{c.title}</div>
                      <div className="text-[11px] text-text-muted mt-0.5 leading-snug">{c.desc}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <Heading icon={<Boxes size={13} />}>Modules it can recommend</Heading>
                <div className="flex flex-wrap gap-1.5">
                  {caps.modules.map((m) => (
                    <span key={m.id} className="badge-accent">{m.name}</span>
                  ))}
                </div>
              </section>

              <section>
                <Heading icon={<MessageSquareText size={13} />}>Try these</Heading>
                <div className="space-y-1.5">
                  {caps.example_prompts.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => { onRunPrompt(q); onClose(); }}
                      className="w-full text-left text-[12px] rounded-lg border border-border bg-bg-card hover:border-accent/50 hover:bg-bg-soft transition-colors px-3 py-2 flex items-center gap-2 group"
                    >
                      <Send size={11} className="text-text-dim group-hover:text-accent-glow shrink-0" />
                      <span className="text-text">{q}</span>
                    </button>
                  ))}
                </div>
              </section>
            </>
          )}

          {tab === 'faqs' && (
            <>
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-dim" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search FAQs…"
                  className="input pl-8"
                />
              </div>
              {Object.entries(filteredFaqs).map(([cat, items]) => (
                <section key={cat}>
                  <Heading icon={<HelpCircle size={13} />}>{cat}</Heading>
                  <div className="space-y-1.5">
                    {items.map((f, i) => <FaqItem key={i} q={f.q} a={f.a} />)}
                  </div>
                </section>
              ))}
              {Object.keys(filteredFaqs).length === 0 && (
                <div className="text-center text-text-dim text-sm py-8">No FAQs match “{query}”.</div>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md bg-bg-card border border-border px-2.5 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-text-dim flex items-center gap-1">{icon}{label}</div>
      <div className="text-[12px] text-text font-medium truncate" title={value}>{value}</div>
    </div>
  );
}

function Heading({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 mb-2 text-[11px] uppercase tracking-wider text-text-muted">
      {icon}{children}
    </div>
  );
}

function TabBtn({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 px-4 py-2.5 border-b-2 transition-colors',
        active ? 'border-accent text-text' : 'border-transparent text-text-muted hover:text-text',
      )}
    >
      {icon}{children}
    </button>
  );
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card overflow-hidden">
      <button onClick={() => setOpen((o) => !o)} className="w-full text-left px-3 py-2 text-[12px] font-medium text-text hover:bg-bg-soft transition-colors">
        {q}
      </button>
      {open && <div className="px-3 pb-2.5 text-[12px] text-text-muted leading-relaxed">{a}</div>}
    </div>
  );
}
