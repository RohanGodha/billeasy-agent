import { Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { Theme } from '@/lib/theme';

export function ThemeToggle({
  theme,
  onToggle,
  className,
}: {
  theme: Theme;
  onToggle: () => void;
  className?: string;
}) {
  const isDark = theme === 'dark';
  return (
    <button
      onClick={onToggle}
      className={cn('icon-btn', className)}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-pressed={isDark}
    >
      {isDark ? <Sun size={15} /> : <Moon size={15} />}
    </button>
  );
}
