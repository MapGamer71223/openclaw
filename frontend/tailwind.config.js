/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        forensic: {
          bg: "rgb(var(--f-bg) / <alpha-value>)",
          bg2: "rgb(var(--f-bg2) / <alpha-value>)",
          panel: "rgb(var(--f-panel) / <alpha-value>)",
          panel2: "rgb(var(--f-panel2) / <alpha-value>)",
          panel3: "rgb(var(--f-panel3) / <alpha-value>)",
          border: "rgb(var(--f-border) / <alpha-value>)",
          border2: "rgb(var(--f-border2) / <alpha-value>)",
          accent: "rgb(var(--f-accent) / <alpha-value>)",
          accentSoft: "rgb(var(--f-accent-soft) / <alpha-value>)",
          violet: "rgb(var(--f-violet) / <alpha-value>)",
          success: "rgb(var(--f-success) / <alpha-value>)",
          warn: "rgb(var(--f-warn) / <alpha-value>)",
          danger: "rgb(var(--f-danger) / <alpha-value>)",
          text: "rgb(var(--f-text) / <alpha-value>)",
          text2: "rgb(var(--f-text2) / <alpha-value>)",
          muted: "rgb(var(--f-muted) / <alpha-value>)",
          faint: "rgb(var(--f-faint) / <alpha-value>)",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(56,189,248,0.15), 0 8px 30px -8px rgba(56,189,248,0.25)",
        glowViolet: "0 0 0 1px rgba(139,92,246,0.15), 0 8px 30px -8px rgba(139,92,246,0.25)",
        panel: "0 1px 0 0 rgba(255,255,255,0.02) inset, 0 12px 32px -16px rgba(0,0,0,0.6)",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: 0 }, "100%": { opacity: 1 } },
        slideUp: { "0%": { opacity: 0, transform: "translateY(8px)" }, "100%": { opacity: 1, transform: "translateY(0)" } },
        scaleIn: { "0%": { opacity: 0, transform: "scale(0.97)" }, "100%": { opacity: 1, transform: "scale(1)" } },
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
        pulseGlow: { "0%,100%": { opacity: 1, boxShadow: "0 0 0 0 rgba(56,189,248,0.4)" }, "50%": { opacity: 0.7, boxShadow: "0 0 0 6px rgba(56,189,248,0)" } },
        spinSlow: { "0%": { transform: "rotate(0deg)" }, "100%": { transform: "rotate(360deg)" } },
      },
      animation: {
        fadeIn: "fadeIn 0.35s ease-out both",
        slideUp: "slideUp 0.4s ease-out both",
        scaleIn: "scaleIn 0.3s ease-out both",
        shimmer: "shimmer 1.6s linear infinite",
        pulseGlow: "pulseGlow 1.8s ease-in-out infinite",
        spinSlow: "spinSlow 2.4s linear infinite",
      },
    },
  },
  plugins: [],
}
