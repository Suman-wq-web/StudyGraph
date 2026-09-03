import type { Config } from "tailwindcss";

// Design tokens map to CSS variables defined in src/app/globals.css so that
// light/dark theming is a single source of truth. See ARCHITECTURE.md
// ("Professional UI direction") for the rationale behind the palette.
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          DEFAULT: "var(--color-base)",
          surface: "var(--color-surface)",
          elevated: "var(--color-elevated)",
          border: "var(--color-border)",
        },
        content: {
          primary: "var(--color-content-primary)",
          secondary: "var(--color-content-secondary)",
          muted: "var(--color-content-muted)",
        },
        accent: {
          teal: "var(--color-accent-teal)",
          indigo: "var(--color-accent-indigo)",
        },
        danger: "var(--color-danger)",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "sans-serif"],
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.97) translateY(4px)" },
          "100%": { opacity: "1", transform: "scale(1) translateY(0)" },
        },
        fadeInBackdrop: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fadeIn 0.28s ease-out",
        "scale-in": "scaleIn 0.18s ease-out",
        "fade-in-backdrop": "fadeInBackdrop 0.18s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
