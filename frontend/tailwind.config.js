/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#24160f",
        amberline: "#f5b329",
        copper: "#9a5a27",
        vellum: "#fffaf0"
      },
      boxShadow: {
        panel: "0 18px 55px rgba(71, 39, 12, 0.12)"
      }
    }
  },
  plugins: []
};
