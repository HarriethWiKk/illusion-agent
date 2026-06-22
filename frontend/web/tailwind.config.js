/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#cc785c',
          hover: '#a9583e',
          light: 'rgba(204, 120, 92, 0.1)',
        },
        secondary: {
          DEFAULT: '#8B7355',
          hover: '#7a6548',
        },
        accent: {
          DEFAULT: '#e8a55a',
          hover: '#d4943e',
        },
        success: {
          DEFAULT: '#5db872',
          hover: '#4da563',
        },
        warning: {
          DEFAULT: '#d4a017',
          hover: '#bf8f14',
        },
        danger: {
          DEFAULT: '#c64545',
          hover: '#b03b3b',
        },
        surface: {
          main: '#faf9f5',
          card: '#ffffff',
          'card-alt': '#f5f0e8',
          hover: '#e6dfd8',
          input: '#ffffff',
        },
        content: {
          primary: '#141413',
          secondary: '#3d3d3a',
          disabled: '#6c6a64',
        },
        border: {
          light: '#e6dfd8',
          medium: '#d4c8b8',
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
        'glow': '0 0 20px rgba(204, 120, 92, 0.15)',
      },
      borderRadius: {
        'sm': '6px',
        'md': '12px',
        'lg': '20px',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.2s ease-out',
      },
    },
  },
  plugins: [],
};
