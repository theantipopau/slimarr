/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          green: '#4CAF50',
          blue: '#1B3A5C',
          accent: '#2196F3',
        },
      },
    },
  },
  plugins: [],
}
