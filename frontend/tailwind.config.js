/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: { DEFAULT: "#6366f1", light: "#818cf8", dark: "#4f46e5" },
        surface: { DEFAULT: "#0f172a", light: "#1e293b", lighter: "#334155" },
      },
    },
  },
  plugins: [],
};
