export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'counter-copilot-theme';

export function getStoredTheme(): Theme | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

export function getSystemTheme(): Theme {
  try {
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

export function getInitialTheme(): Theme {
  return getStoredTheme() ?? getSystemTheme();
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.classList.toggle('light', theme === 'light');
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // storage unavailable
  }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', theme === 'dark' ? '#0a0d12' : '#f7f8fa');
}

export function themeColor(token: string, fallback = '#3b82f6'): string {
  try {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue(`--c-${token}`)
      .trim();
    return v ? `rgb(${v})` : fallback;
  } catch {
    return fallback;
  }
}
