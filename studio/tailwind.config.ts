import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        studio: {
          bg: "var(--studio-bg)",
          panel: "var(--studio-panel)",
          panelAlt: "var(--studio-panel-alt)",
          border: "var(--studio-border)",
          text: "var(--studio-text)",
          muted: "var(--studio-muted)",
          accent: "var(--studio-cyan)",
          magenta: "var(--studio-magenta)",
          pass: "var(--studio-lime)",
          warn: "var(--studio-warn)",
          fail: "var(--studio-fail)"
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
