import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--canvas)",
        card: "var(--card)",
        panel: "var(--panel)",
        rail: { DEFAULT: "var(--rail)", 2: "var(--rail-2)", text: "var(--rail-text)" },
        ink: { DEFAULT: "var(--ink)", muted: "var(--slate)" },
        "ink-muted": "var(--slate)",
        line: { DEFAULT: "var(--line)", strong: "var(--line-strong)" },
        accent: { DEFAULT: "var(--accent)", deep: "var(--accent-deep)", soft: "var(--accent-soft)", light: "var(--accent-soft)", dark: "var(--accent-deep)" },
        terracotta: { DEFAULT: "var(--terracotta)", soft: "var(--terracotta-soft)" },
        saffron: { DEFAULT: "var(--saffron)", soft: "var(--saffron-soft)" },
        ok: { DEFAULT: "var(--ok)", soft: "var(--ok-soft)" },
        warn: { DEFAULT: "var(--warn)", soft: "var(--warn-soft)" },
        danger: { DEFAULT: "var(--danger)", soft: "var(--danger-soft)" },
        synthetic: "var(--terracotta)",
      },
      boxShadow: { card: "var(--shadow)" },
      borderRadius: { card: "var(--radius)" },
      fontFamily: { sans: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "Noto Sans", "sans-serif"] },
    },
  },
  plugins: [],
};
export default config;
