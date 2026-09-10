import { useEffect, useState } from 'react';
import { SessionsSidebar } from '@/features/sessions/SessionsSidebar';
import { ChatPane } from '@/features/chat/ChatPane';
import { CandidatesPanel } from '@/features/candidates/CandidatesPanel';
import { CounterDrawer } from '@/features/drawer/CounterDrawer';
import { useUi } from '@/store/uiStore';
import { api } from '@/lib/api';
import { LogOut, Activity, Server, BookOpen, MessageSquare, Sparkles, Users, Library } from 'lucide-react';
import { GuidePanel } from '@/features/guide/GuidePanel';
import { KnowledgeModal } from '@/features/knowledge/KnowledgeModal';
import { useAgentStream } from '@/hooks/useAgentStream';
import { useTheme } from '@/hooks/useTheme';
import { ThemeToggle } from '@/components/ThemeToggle';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { cn } from '@/lib/cn';

type MobilePane = 'sessions' | 'chat' | 'candidates';

export function Dashboard({ onLogout }: { onLogout: () => void }) {
  const selected = useUi((s) => s.selectedCounterId);
  const sessionId = useUi((s) => s.sessionId);
  const candidates = useUi((s) => s.candidates);
  const [guideOpen, setGuideOpen] = useState(false);
  const [kbOpen, setKbOpen] = useState(false);
  const [mobilePane, setMobilePane] = useState<MobilePane>('chat');
  const { theme, toggle } = useTheme();
  const { run } = useAgentStream();
  const [status, setStatus] = useState<{
    datasource_active: string;
    datasource_healthy: boolean;
    llm_providers: Record<string, boolean>;
  } | null>(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => null);
  }, []);

  const llmActive = status
    ? Object.entries(status.llm_providers)
        .filter(([k, v]) => v && k !== 'mock')
        .map(([k]) => k.toUpperCase())
    : [];
  // With no LLM key the agent still runs end to end — planning and phrasing are
  // deterministic rather than model-written. Say that plainly rather than showing a
  // cryptic "Mock", so a reviewer knows exactly what they are looking at.
  const isDemoMode = llmActive.length === 0;
  const llmLabel = isDemoMode ? 'Demo mode' : llmActive.join(' + ');
  const llmTitle = isDemoMode
    ? 'No LLM key configured. The full agent runs — planning, tools, critic, scoring and compliance validation are all real — but the plan and summary come from a deterministic planner instead of a model. Set ANTHROPIC_API_KEY, GEMINI_API_KEY or GROQ_API_KEY to route to a live model.'
    : `Live model routing: ${llmActive.join(' + ')}`;

  return (
    <div className="h-screen flex flex-col bg-bg text-text overflow-hidden">
      <header className="shrink-0 h-12 flex items-center justify-between gap-2 px-3 sm:px-4 border-b border-border bg-bg-soft/60 backdrop-blur">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="h-7 w-7 shrink-0 rounded-md bg-accent/15 border border-accent-soft/40 flex items-center justify-center">
            <Activity size={14} className="text-accent-glow" />
          </div>
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="text-sm font-semibold whitespace-nowrap">Counter Copilot</span>
            <span className="hidden md:inline text-[11px] text-text-dim truncate">
              Revenue Assurance · Rohan, Area Partner Manager — Mumbai West
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-3 text-[11px] text-text-muted">
          {status && (
            <>
              <span className="badge hidden lg:inline-flex">
                <Server size={11} /> {status.datasource_active}
              </span>
              <span
                className={cn(
                  'hidden md:inline-flex',
                  status.datasource_healthy ? 'badge-pos' : 'badge-neg',
                )}
              >
                {status.datasource_healthy ? 'Data OK' : 'Data Degraded'}
              </span>
              <span
                className={isDemoMode ? 'badge hidden sm:inline-flex' : 'badge-accent hidden sm:inline-flex'}
                title={llmTitle}
              >
                LLM: {llmLabel}
              </span>
            </>
          )}
          <button
            onClick={() => setKbOpen(true)}
            className="btn-ghost text-xs px-2 sm:px-3"
            title="Payments knowledge base — ask about GST e-invoicing, settlement norms, NCMC, merchant KYC"
          >
            <Library size={13} />
            <span className="hidden sm:inline">Knowledge</span>
          </button>
          <button
            onClick={() => setGuideOpen(true)}
            className="btn-ghost text-xs px-2 sm:px-3"
            title="What can Counter Copilot do?"
          >
            <BookOpen size={13} />
            <span className="hidden sm:inline">Guide</span>
          </button>
          <ThemeToggle theme={theme} onToggle={toggle} />
          <button onClick={onLogout} className="btn-ghost text-xs px-2 sm:px-3" title="Sign out">
            <LogOut size={13} />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-hidden lg:grid lg:grid-cols-[260px_1fr_440px] xl:grid-cols-[300px_1fr_460px]">
        <aside
          className={cn(
            'h-full border-r border-border overflow-hidden lg:block',
            mobilePane === 'sessions' ? 'block' : 'hidden',
          )}
        >
          <ErrorBoundary label="Conversations">
            <SessionsSidebar />
          </ErrorBoundary>
        </aside>

        <section
          className={cn(
            'h-full overflow-hidden lg:block',
            mobilePane === 'chat' ? 'block' : 'hidden',
          )}
        >
          <ErrorBoundary label="Chat">
            <ChatPane />
          </ErrorBoundary>
        </section>

        <aside
          className={cn(
            'h-full border-l border-border overflow-hidden lg:block',
            mobilePane === 'candidates' ? 'block' : 'hidden',
          )}
        >
          <ErrorBoundary label="Candidates">
            <CandidatesPanel />
          </ErrorBoundary>
        </aside>
      </main>

      <nav className="lg:hidden shrink-0 flex items-stretch border-t border-border bg-bg-soft/85 backdrop-blur pb-safe">
        <NavBtn
          active={mobilePane === 'sessions'}
          onClick={() => setMobilePane('sessions')}
          icon={<MessageSquare size={17} />}
          label="Chats"
        />
        <NavBtn
          active={mobilePane === 'chat'}
          onClick={() => setMobilePane('chat')}
          icon={<Sparkles size={17} />}
          label="Copilot"
        />
        <NavBtn
          active={mobilePane === 'candidates'}
          onClick={() => setMobilePane('candidates')}
          icon={<Users size={17} />}
          label="Candidates"
          count={candidates.length}
        />
      </nav>

      {selected && (
        <ErrorBoundary label="Counter 360" resetKey={selected}>
          <CounterDrawer counterId={selected} />
        </ErrorBoundary>
      )}
      {guideOpen && (
        <ErrorBoundary label="Guide">
          <GuidePanel
            onClose={() => setGuideOpen(false)}
            onRunPrompt={(q) => {
              setMobilePane('chat');
              run({ query: q, sessionId });
            }}
          />
        </ErrorBoundary>
      )}
      {kbOpen && (
        <ErrorBoundary label="Knowledge Base">
          <KnowledgeModal onClose={() => setKbOpen(false)} />
        </ErrorBoundary>
      )}
    </div>
  );
}

function NavBtn({
  active,
  onClick,
  icon,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  count?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[11px] font-medium transition-colors',
        active ? 'text-accent-glow' : 'text-text-muted hover:text-text',
      )}
      aria-current={active ? 'page' : undefined}
    >
      <span className="relative">
        {icon}
        {count != null && count > 0 && (
          <span className="absolute -right-2.5 -top-1.5 min-w-[15px] h-[15px] px-1 rounded-full bg-accent text-white text-[9px] leading-[15px] text-center font-semibold">
            {count}
          </span>
        )}
      </span>
      <span>{label}</span>
      {active && <span className="absolute top-0 left-1/2 -translate-x-1/2 h-0.5 w-8 rounded-full bg-accent-glow" />}
    </button>
  );
}
