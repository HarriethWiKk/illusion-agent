/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#6366F1',
          hover: '#4F46E5',
          light: 'rgba(99, 102, 241, 0.1)',
        },
        secondary: {
          DEFAULT: '#8B5CF6',
          hover: '#7C3AED',
        },
        accent: {
          DEFAULT: '#F59E0B',
          hover: '#D97706',
        },
        success: {
          DEFAULT: '#10B981',
          hover: '#059669',
        },
        warning: {
          DEFAULT: '#F59E0B',
          hover: '#D97706',
        },
        danger: {
          DEFAULT: '#EF4444',
          hover: '#DC2626',
        },
        surface: {
          main: '#F8FAFC',
          card: '#FFFFFF',
          'card-alt': '#F1F5F9',
          hover: '#E2E8F0',
          input: '#FFFFFF',
        },
        content: {
          primary: '#1E293B',
          secondary: '#64748B',
          disabled: '#94A3B8',
        },
        border: {
          light: 'rgba(148, 163, 184, 0.2)',
          medium: 'rgba(148, 163, 184, 0.4)',
        },
      },
      fontFamily: {
        display: ['Playfair Display', 'Georgia', 'serif'],
        body: ['Inter', 'Inter Fallback', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'soft': '0 1px 2px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.06)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05)',
        'glow': '0 0 20px rgba(99, 102, 241, 0.15)',
      },
      borderRadius: {
        'sm': '6px',
        'md': '12px',
        'lg': '20px',
      },
    },
  },
  plugins: [],
};
