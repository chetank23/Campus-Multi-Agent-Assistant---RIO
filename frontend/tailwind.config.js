/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0f5fc',
          100: '#e1ecf8',
          200: '#c5daf2',
          300: '#99bfe9',
          400: '#649cdc',
          500: '#3c7ecc',
          600: '#1e5ca8',
          700: '#174786',
          800: '#153c6e',
          900: '#14345c',
          950: '#0b1d36',
        },
        navy: {
          50: '#f5f7fa',
          100: '#eaeef5',
          200: '#d0daea',
          300: '#a7bcdc',
          400: '#7799c9',
          500: '#5479b4',
          600: '#3d5e97',
          700: '#314b7b',
          800: '#2a3f65',
          900: '#1c2942',
          950: '#101726',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        'subtle': '0 1px 2px 0 rgba(0, 0, 0, 0.04), 0 1px 3px 0 rgba(0, 0, 0, 0.02)',
        'card': '0 1px 3px 0 rgba(15, 23, 42, 0.06), 0 1px 2px -1px rgba(15, 23, 42, 0.04)',
        'elevated': '0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.04)',
        'modal': '0 20px 25px -5px rgba(15, 23, 42, 0.12), 0 8px 10px -6px rgba(15, 23, 42, 0.08)',
      },
    },
  },
  plugins: [],
};
