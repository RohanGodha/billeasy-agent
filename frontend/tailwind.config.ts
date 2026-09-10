import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    screens: {
      xs: '480px',
      sm: '640px',
      md: '768px',
      lg: '1024px',
      xl: '1280px',
      '2xl': '1536px',
    },
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        bg: {
          DEFAULT: 'rgb(var(--c-bg) / <alpha-value>)',
          soft: 'rgb(var(--c-bg-soft) / <alpha-value>)',
          card: 'rgb(var(--c-bg-card) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--c-border) / <alpha-value>)',
          strong: 'rgb(var(--c-border-strong) / <alpha-value>)',
        },
        text: {
          DEFAULT: 'rgb(var(--c-text) / <alpha-value>)',
          muted: 'rgb(var(--c-text-muted) / <alpha-value>)',
          dim: 'rgb(var(--c-text-dim) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--c-accent) / <alpha-value>)',
          soft: 'rgb(var(--c-accent-soft) / <alpha-value>)',
          glow: 'rgb(var(--c-accent-glow) / <alpha-value>)',
        },
        positive: { DEFAULT: 'rgb(var(--c-positive) / <alpha-value>)' },
        warning: { DEFAULT: 'rgb(var(--c-warning) / <alpha-value>)' },
        danger: { DEFAULT: 'rgb(var(--c-danger) / <alpha-value>)' },
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
      },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,0.25)',
        pop: '0 12px 40px -12px rgba(0,0,0,0.6)',
        glow: '0 0 0 1px rgba(96,165,250,0.25), 0 8px 28px -8px rgba(59,130,246,0.35)',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0', transform: 'translateY(2px)' }, to: { opacity: '1', transform: 'none' } },
        'pulse-dot': { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.4' } },
        'slide-in-right': { from: { opacity: '0', transform: 'translateX(16px)' }, to: { opacity: '1', transform: 'none' } },
        'slide-up': { from: { opacity: '0', transform: 'translateY(10px)' }, to: { opacity: '1', transform: 'none' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
      },
      animation: {
        'fade-in': 'fade-in 180ms ease-out',
        'pulse-dot': 'pulse-dot 1.4s ease-in-out infinite',
        'slide-in-right': 'slide-in-right 220ms cubic-bezier(0.16,1,0.3,1)',
        'slide-up': 'slide-up 200ms cubic-bezier(0.16,1,0.3,1)',
      },
    },
  },
  plugins: [],
};

export default config;
