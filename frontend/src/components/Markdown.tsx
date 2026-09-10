import { Fragment } from 'react';
import { cn } from '@/lib/cn';

/**
 * Minimal zero-dependency markdown renderer for assistant replies.
 *
 * The agent summary, FAQ and knowledge-base answers are written as small markdown —
 * **bold**, `code`, *italic*, `- ` bullets and `#` headings. The chat bubble renders
 * text verbatim, so those markers were showing up as literal `**text**`. We only need
 * enough markdown to cover what the backend actually emits; no full parser.
 */

const INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(INLINE_RE);
  return parts.map((part, i) => {
    if (!part) return null;
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={i}
          className="rounded bg-bg-soft border border-border px-1 py-0.5 text-[0.85em] font-mono"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

function isBullet(line: string): boolean {
  return /^\s*[-•]\s+/.test(line);
}

function isHeading(line: string): boolean {
  return /^#{1,6}\s+/.test(line);
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  const lines = text.split('\n');
  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];

  const flushBullets = () => {
    if (bullets.length === 0) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="my-1 list-disc pl-4 space-y-0.5">
        {bullets.map((b, i) => (
          <li key={i}>{renderInline(b.replace(/^\s*[-•]\s+/, ''))}</li>
        ))}
      </ul>,
    );
    bullets = [];
  };

  lines.forEach((line, i) => {
    const trimmed = line.trim();
    if (trimmed === '') {
      flushBullets();
      return;
    }
    if (isBullet(line)) {
      bullets.push(line);
      return;
    }
    flushBullets();
    if (isHeading(line)) {
      const level = line.match(/^#{1,6}/)![0].length;
      const content = trimmed.replace(/^#{1,6}\s+/, '');
      const Tag = level === 1 ? 'h1' : level === 2 ? 'h2' : 'h3';
      blocks.push(
        <Tag
          key={`h-${i}`}
          className={cn(
            'font-semibold text-text',
            level === 1 && 'text-base',
            level === 2 && 'text-sm',
            level >= 3 && 'text-sm',
          )}
        >
          {renderInline(content)}
        </Tag>,
      );
      return;
    }
    blocks.push(<p key={`p-${i}`}>{renderInline(trimmed)}</p>);
  });
  flushBullets();

  return <div className={cn('space-y-1.5', className)}>{blocks}</div>;
}