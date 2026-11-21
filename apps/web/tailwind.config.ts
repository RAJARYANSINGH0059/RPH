import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: { DEFAULT: "#1f5fa8", light: "#e7eff9", dark: "#174a84" },
        "ink-muted": "#5b6775",
        ink: { DEFAULT: "#1d2733", muted: "#5b6775" },
        line: "#dfe4ea",
        synthetic: "#8a1c1c",
      },
    },
  },
  plugins: [],
};
export default config;
