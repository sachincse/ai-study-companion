import typography from '@tailwindcss/typography'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        brand: {
          50: '#eef0fe',
          100: '#e0e3fd',
          200: '#c3c8fb',
          300: '#9fa7f6',
          400: '#7b84ee',
          500: '#5b5bd6',
          600: '#4946b5',
          700: '#3b3894',
          800: '#2e2c73',
          900: '#1f1e4f',
        },
        ink: { 950: '#070c18', 900: '#0b1220', 800: '#111a2e', 700: '#1a2440', 600: '#243150', 500: '#3b4a6b' },
        mint: { 50: '#e0f5ea', 600: '#19764d' },
        amber: { 50: '#fff0d9', 600: '#9a5a08' },
        rose: { 50: '#fbe5ef', 600: '#a42c62' },
        sky: { 50: '#e2f1fb', 600: '#1d659a' },
        plum: { 50: '#eee5fc', 600: '#7842b8' },
        teal: { 50: '#e6f3f0', 600: '#28756b' },
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)',
        pop: '0 12px 32px -12px rgba(15, 23, 42, 0.25)',
      },
      borderRadius: { xl: '0.875rem', '2xl': '1.125rem' },
      keyframes: {
        'fade-up': { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'pulse-dot': { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0.4' } },
      },
      animation: { 'fade-up': 'fade-up 0.25s ease-out both', 'pulse-dot': 'pulse-dot 1.6s ease-in-out infinite' },
    },
  },
  plugins: [typography],
}
