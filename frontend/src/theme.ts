import { extendTheme, type ThemeConfig } from '@chakra-ui/react';

const config: ThemeConfig = { initialColorMode: 'light', useSystemColorMode: false };

// Colours live in CSS variables (src/index.css) so Tailwind and Chakra share them;
// Chakra's colour mode flips `data-theme` on <html> (see App.tsx).
export const theme = extendTheme({
  config,
  fonts: {
    heading: `'DM Sans', system-ui, sans-serif`,
    body: `'DM Sans', system-ui, sans-serif`,
    mono: `'DM Mono', ui-monospace, monospace`,
  },
  styles: {
    global: {
      'html, body': { bg: 'var(--bg)', color: 'var(--ink)' },
    },
  },
  components: {
    Tooltip: {
      baseStyle: {
        bg: 'var(--ink)',
        color: 'var(--card)',
        '--popper-arrow-bg': 'var(--ink)',
        borderRadius: '8px',
        fontWeight: 500,
        fontSize: '13px',
        px: '10px',
        py: '5px',
      },
    },
  },
});
