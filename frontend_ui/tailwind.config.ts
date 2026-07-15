import type { Config } from 'tailwindcss'

export default {
  theme: {
    extend: {
      colors: {
        brand: {
          dark: '#3C3C3B',
          blue: '#0496CD',
          yellow: '#F5C418',
          red: '#D12928',
          light: '#DDE1E5',
        },
      },
      fontFamily: {
        sans: ['Segoe UI', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        executive: '0 1px 3px rgba(60, 60, 59, 0.08), 0 4px 12px rgba(60, 60, 59, 0.06)',
        card: '0 2px 8px rgba(60, 60, 59, 0.1)',
      },
    },
  },
} satisfies Config
