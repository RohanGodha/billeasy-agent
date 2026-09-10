import { useEffect, useRef, useState } from 'react';
import type { Counter, DraftRecord } from '@/lib/types';
import { cn } from '@/lib/cn';
import {
  Edit3,
  Save,
  X,
  Copy,
  Check,
  MessageCircle,
  AlertTriangle,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { resolvePhone, hasMappedPhone, whatsappSendUrl } from '@/lib/demoPhones';
import { useUi } from '@/store/uiStore';
import { useOutreachDraft } from './useOutreachDraft';

export function WhatsAppPreview({
  counter,
  draft,
}: {
  counter: Counter;
  draft: DraftRecord;
}) {
  const sessionId = useUi((s) => s.sessionId);
  const isStreaming = useUi((s) => s.isStreaming);
  const record = useOutreachDraft(sessionId, draft.counter_id);

  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draft.message);
  const [savedText, setSavedText] = useState(draft.message);
  const [sent, setSent] = useState(false);
  const [copied, setCopied] = useState(false);
  /** True once an approved draft is edited — approval no longer covers this text. */
  const [staleApproval, setStaleApproval] = useState(false);

  // The stored message wins over the streamed one: a draft edited in an earlier
  // review is what the supervisor would actually receive.
  const storedMessage = record.row?.message;
  useEffect(() => {
    if (storedMessage === undefined || editing) return;
    setSavedText(storedMessage);
    setText(storedMessage);
    // Deliberately keyed on the stored message alone: re-running this while the
    // manager is mid-edit would overwrite what they are typing.
  }, [storedMessage]);

  // A drawer opened mid-run finds no row: the responder writes the batch as the
  // run ends. Re-read once streaming stops so the manager is not left with a
  // draft they cannot approve.
  const syncRef = useRef(record.sync);
  syncRef.current = record.sync;
  const reload = record.reload;
  useEffect(() => {
    if (!isStreaming && syncRef.current === 'absent') reload();
  }, [isStreaming, reload]);

  const phone = resolvePhone(counter?.name, counter?.phone);
  const mapped = hasMappedPhone(counter?.name);
  const onRecord = record.sync === 'ready';
  const approved = record.approved && !staleApproval;
  const dirty = editing && text !== savedText;

  async function copy() {
    try {
      await navigator.clipboard.writeText(savedText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {/* clipboard unavailable */}
  }

  async function saveEdit() {
    const next = text;
    const ok = await record.save(next);
    if (!ok) return; // stay in the editor; the error banner explains why
    setSavedText(next);
    setEditing(false);
    if (record.approved) setStaleApproval(true);
  }

  async function approveDraft() {
    const ok = await record.approve();
    if (ok) setStaleApproval(false);
  }

  async function sendOnWhatsApp() {
    if (!approved) return;
    try {
      await navigator.clipboard.writeText(savedText);
    } catch {/* clipboard unavailable */}
    window.open(whatsappSendUrl(phone, savedText), '_blank', 'noopener,noreferrer');
    setSent(true);
    setTimeout(() => setSent(false), 2500);
  }

  return (
    <div>
      <div className="mx-auto max-w-md">
        {/* Where this draft stands on the counter record */}
        <div className="mb-2 flex items-center justify-between gap-2" aria-live="polite">
          {record.sync === 'loading' ? (
            <span className="badge">
              <Loader2 size={11} className="animate-spin" /> Reading draft record…
            </span>
          ) : approved ? (
            <span className="badge-pos">
              <ShieldCheck size={11} /> Approved by you
            </span>
          ) : record.approved && staleApproval ? (
            <span className="badge-warn">
              <AlertTriangle size={11} /> Edited after approval
            </span>
          ) : (
            <span className="badge">Draft · awaiting your approval</span>
          )}
          {dirty && <span className="badge-warn">Unsaved edit</span>}
          {!dirty && !editing && onRecord && (
            <span className="text-[10px] text-text-dim">Saved to the counter record</span>
          )}
        </div>

        <div
          className={cn(
            'rounded-2xl bg-[#0b1218] border overflow-hidden shadow-lg',
            approved ? 'border-positive/60 ring-1 ring-positive/30' : 'border-border',
          )}
        >
          {/* Status bar */}
          <div className="h-6 bg-black/60 flex items-center justify-center text-[10px] text-text-muted">
            ── Live Preview ──
          </div>
          {/* Header */}
          <div className="px-3 py-2 bg-[#1f2c33] flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-accent/30 flex items-center justify-center text-[12px] text-white">
              {(counter.name || '?').slice(0, 1)}
            </div>
            <div>
              <div className="text-[12px] font-medium text-white">{counter.name}</div>
              <div className="text-[10px] text-text-muted">Counter supervisor</div>
            </div>
          </div>
          {/* Body */}
          <div className="px-3 py-4 bg-[#0b1218] min-h-[140px]">
            {editing ? (
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={5}
                className="w-full bg-[#005c4b]/30 border border-accent/30 text-[13px] text-white px-3 py-2 rounded-md focus:outline-none focus:ring-1 focus:ring-accent resize-none"
                autoFocus
                aria-label="Draft message to the counter supervisor"
              />
            ) : (
              <div
                className={cn(
                  'inline-block max-w-[88%] bg-[#005c4b] text-white text-[13px] px-3 py-2 rounded-lg rounded-tl-sm leading-relaxed',
                  'shadow-md',
                )}
              >
                {savedText}
                <div className="text-[9px] text-white/60 mt-1 text-right">
                  {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="mt-3 flex flex-wrap gap-2">
          {editing ? (
            <>
              <button
                onClick={() => { setEditing(false); setText(savedText); record.clearError(); }}
                className="btn-ghost"
                disabled={record.busy === 'save'}
              >
                <X size={13} /> Cancel
              </button>
              <button
                onClick={saveEdit}
                className="btn-primary"
                disabled={record.busy === 'save' || !onRecord}
                title={
                  onRecord
                    ? 'Saves the edit to the draft record'
                    : 'This draft is not on the counter record yet'
                }
              >
                {record.busy === 'save'
                  ? <Loader2 size={13} className="animate-spin" />
                  : <Save size={13} />}
                {record.busy === 'save' ? 'Saving…' : 'Save'}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => { record.clearError(); setEditing(true); }}
                className="btn-outline"
                disabled={!onRecord}
                title={
                  onRecord
                    ? 'Edit the message before it goes to the supervisor'
                    : 'This draft is not on the counter record yet'
                }
              >
                <Edit3 size={13} /> Edit
              </button>
              <button onClick={copy} className="btn-outline">
                {copied ? <Check size={13} className="text-positive" /> : <Copy size={13} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
              {!approved && (
                <button
                  onClick={approveDraft}
                  className="btn-primary"
                  disabled={record.busy === 'approve' || !onRecord}
                  title={
                    onRecord
                      ? 'Record your approval against this draft'
                      : 'This draft is not on the counter record yet'
                  }
                >
                  {record.busy === 'approve'
                    ? <Loader2 size={13} className="animate-spin" />
                    : <ShieldCheck size={13} />}
                  {record.busy === 'approve'
                    ? 'Approving…'
                    : staleApproval ? 'Re-approve edit' : 'Approve'}
                </button>
              )}
              <button
                onClick={sendOnWhatsApp}
                disabled={!approved || !phone}
                className={cn(approved ? 'btn-primary' : 'btn-outline', sent && 'opacity-80')}
                title={
                  !approved
                    ? 'Approve the draft first'
                    : phone
                      ? 'Opens WhatsApp with the message pre-filled — you press Send there'
                      : 'No supervisor number on file for this counter'
                }
              >
                {sent ? <Check size={13} /> : <MessageCircle size={13} />}
                {sent ? 'Opened in WhatsApp' : 'Send on WhatsApp'}
              </button>
            </>
          )}
        </div>

        {record.error && (
          <div
            role="alert"
            className="mt-2 flex items-start gap-2 text-[11px] rounded-md bg-danger/10 border border-danger/30 text-danger px-3 py-2 leading-relaxed"
          >
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            <span className="flex-1">{record.error}</span>
            <button onClick={record.reload} className="icon-btn p-1" title="Retry">
              <RefreshCw size={12} />
            </button>
          </div>
        )}

        {record.sync === 'absent' && (
          <p className="mt-2 text-[11px] text-text-dim leading-relaxed">
            This draft is not on the counter record yet — it is written when the run
            finishes. Reopen the counter once the agent is done to edit or approve it.
          </p>
        )}

        <p className="mt-2 text-[11px] text-text-dim leading-relaxed">
          {approved
            ? 'Approved. WhatsApp opens with the message pre-filled — you press Send there. Counter Copilot never sends anything itself.'
            : 'You approve first, then WhatsApp opens with the message pre-filled. Counter Copilot never sends anything itself.'}
        </p>

        {!mapped && phone && (
          <p className="mt-2 text-[11px] text-text-dim leading-relaxed">
            Note: this counter uses a synthetic demo number, so WhatsApp may show
            “not on WhatsApp”. The message is copied to your clipboard either way.
          </p>
        )}

        {draft.compliance && !draft.compliance.ok && (draft.compliance.ungrounded || []).length > 0 && (
          <div className="mt-3 text-[11px] rounded-md bg-warning/10 border border-warning/30 text-warning px-3 py-2 leading-relaxed">
            Compliance validator stripped settlement/TPV figures the source data does not support:&nbsp;
            <span className="font-mono">{(draft.compliance.ungrounded || []).join(', ')}</span>
          </div>
        )}
      </div>
    </div>
  );
}
