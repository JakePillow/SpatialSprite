import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        studio: {
          bg: "#101114",
          panel: "#17191d",
          panelAlt: "#1d2026",
          border: "#2a2e36",
          text: "#e8edf3",
          muted: "#8d99a8",
          accent: "#4ea1ff",
          pass: "#38b77a",
          warn: "#d7a642",
          fail: "#ef5d5d"
        }
      },
      fontFamily: {
        ui: ["Inter", "Segoe UI", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"]
      }
    }
  },
  plugins: []
} satisfies Config;
