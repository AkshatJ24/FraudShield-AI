/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // Chakra ships its own CSS reset; Tailwind's would fight it.
  corePlugins: { preflight: false },
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        card: 'var(--card)',
        ink: 'var(--ink)',
        muted: 'var(--muted)',
        muted2: 'var(--muted-2)',
        line: 'var(--line)',
        brand: 'var(--brand)',
        brand2: 'var(--brand-2)',
        brandsoft: 'var(--brand-soft)',
      },
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"DM Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: { card: 'var(--shadow)' },
      keyframes: {
        fadeUp: { from: { opacity: '0', transform: 'translateY(14px)' }, to: { opacity: '1', transform: 'none' } },
        slideIn: { from: { opacity: '0', transform: 'translateX(70px)' }, to: { opacity: '1', transform: 'none' } },
        slideOut: { to: { opacity: '0', transform: 'translateX(-90px)' } },
        sweep: { to: { transform: 'rotate(360deg)' } },
        dotPing: { from: { transform: 'scale(1)', opacity: '.7' }, to: { transform: 'scale(3.2)', opacity: '0' } },
        pulseRing: { '0%,100%': { boxShadow: '0 0 0 0 var(--brand-soft)' }, '50%': { boxShadow: '0 0 0 12px var(--brand-soft)' } },
        blink: { '0%,100%': { opacity: '1' }, '50%': { opacity: '.35' } },
        cardIn: { from: { opacity: '0', transform: 'translateY(-34px) rotate(-3deg) scale(1.02)' }, to: { opacity: '1' } },
      },
      animation: {
        'fade-up': 'fadeUp .6s cubic-bezier(.2,.8,.2,1) both',
        'fade-up-late': 'fadeUp .6s .25s cubic-bezier(.2,.8,.2,1) both',
        'slide-in': 'slideIn .7s cubic-bezier(.2,.8,.2,1) both',
        'slide-out': 'slideOut .45s cubic-bezier(.6,0,.4,1) forwards',
        sweep: 'sweep 60s linear infinite',
        'dot-ping': 'dotPing 1.4s ease-out forwards',
        'pulse-ring': 'pulseRing 1.1s ease-in-out infinite',
        blink: 'blink 1.6s ease-in-out infinite',
        'card-in': 'cardIn .6s cubic-bezier(.2,.8,.2,1)',
      },
    },
  },
  plugins: [],
};
