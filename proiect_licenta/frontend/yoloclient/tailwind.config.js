/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        emerald: {
          50:  '#edfff6',
          100: '#d6ffeb',
          200: '#a0ffd3',
          300: '#69f0ae',
          400: '#2bec84',
          500: '#00e676',
          600: '#00c853',
          700: '#00a844',
          800: '#008836',
          900: '#006b2b',
          950: '#003d18',
        },
      },
    },
  },
  plugins: [],
};
