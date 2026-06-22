/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#2a9d99',    /* 青绿色 - 清新主色 */
          hover: '#238b87',     /* 深青绿 */
          light: 'rgba(42, 157, 153, 0.1)',
        },
        secondary: {
          DEFAULT: '#7c6fb0',   /* 淡紫色 */
          hover: '#6b5ea0',
        },
        accent: {
          DEFAULT: '#e8856c',   /* 珊瑚橙 - 强调色 */
          hover: '#d4745b',
        },
        success: {
          DEFAULT: '#4caf7d',   /* 薄荷绿 */
          hover: '#3d9e6e',
        },
        warning: {
          DEFAULT: '#e8a84c',   /* 琥珀黄 */
          hover: '#d4973b',
        },
        danger: {
          DEFAULT: '#d45b5b',   /* 柔和红 */
          hover: '#c34a4a',
        },
        surface: {
          main: '#ffffff',      /* 纯白背景 */
          card: '#ffffff',
          'card-alt': '#f7f8fa', /* 极淡灰蓝 */
          hover: '#eef0f4',     /* 淡灰蓝悬停 */
          input: '#ffffff',
        },
        content: {
          primary: '#1a1d23',   /* 深灰黑 */
          secondary: '#4a5068', /* 蓝灰 */
          disabled: '#8b92a8',  /* 浅蓝灰 */
        },
        border: {
          light: '#e8ebf0',     /* 淡蓝灰边框 */
          medium: '#d0d5e0',    /* 中蓝灰边框 */
        },
        /* 粉彩色块 - 用于装饰和高亮 */
        pastel: {
          mint: '#d4f5e0',      /* 薄荷绿 */
          lilac: '#e8dff5',     /* 淡紫 */
          cream: '#fef7e6',     /* 奶油黄 */
          pink: '#fde0e8',      /* 粉红 */
          sky: '#dcecfa',       /* 天蓝 */
          coral: '#fde0d4',     /* 珊瑚 */
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
        'glow': '0 0 20px rgba(42, 157, 153, 0.15)',
      },
      borderRadius: {
        'xs': '4px',
        'sm': '6px',
        'md': '8px',
        'lg': '12px',
        'xl': '16px',
        'pill': '9999px',
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
