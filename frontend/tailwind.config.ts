import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "rgb(var(--paper) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        lint: "rgb(var(--lint) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        faint: "rgb(var(--faint) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-soft": "rgb(var(--accent-soft) / <alpha-value>)",
        link: "rgb(var(--link) / <alpha-value>)",
        communicatiekleur: "rgb(var(--communicatiekleur) / <alpha-value>)",
        gold: "rgb(var(--gold) / <alpha-value>)",
        succes: "rgb(var(--succes) / <alpha-value>)",
        waarschuwing: "rgb(var(--waarschuwing) / <alpha-value>)",
        fout: "rgb(var(--fout) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
      },
      fontFamily: {
        display: ["var(--font-sans)", "system-ui", "sans-serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        // Rijkshuisstijl: button ≈ 10% van de hoogte (48px), formulierveld ≈ 5%.
        button: "5px",
        field: "3px",
        // Vormelement: één grote afgeronde hoek als signatuur (RH-radius-stap).
        vorm: "32px",
      },
      maxWidth: {
        prose: "72ch",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        rise: "rise 0.5s cubic-bezier(0.16, 1, 0.3, 1) both",
      },
    },
  },
  plugins: [],
};

export default config;
