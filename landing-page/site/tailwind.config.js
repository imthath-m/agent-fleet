/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./main.js"],
  theme: {
    extend: {
      colors: {
        ink: "#0F172A",
        body: "#334155",
        muted: "#64748B",
        bg: "#FAFAF7",
        surface: "#FFFFFF",
        border: "#E2E8F0",
        accent: "#4F46E5",
        "accent-hover": "#4338CA",
        "accent-soft": "#EEF2FF",
        success: "#059669",
        panel: "#0B1220",
        "panel-text": "#C9D4E3",
        // Per-product hues
        triage: "#0284C7",
        "triage-soft": "#E0F2FE",
        payable: "#059669",
        "payable-soft": "#D1FAE5",
        prospect: "#D97706",
        "prospect-soft": "#FEF3C7",
        followthrough: "#7C3AED",
        "followthrough-soft": "#EDE9FE",
        redline: "#E11D48",
        "redline-soft": "#FFE4E6",
      },
      fontFamily: {
        display: ['"Space Grotesk"', "system-ui", "-apple-system", "sans-serif"],
        sans: ['"Inter"', "system-ui", "-apple-system", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      maxWidth: {
        "6xl": "72rem",
      },
    },
  },
  // Product-hue utility classes are applied dynamically via data attributes /
  // string interpolation in the markup, so safelist every hue variant.
  safelist: [
    "bg-triage", "bg-triage-soft", "text-triage", "border-triage",
    "bg-payable", "bg-payable-soft", "text-payable", "border-payable",
    "bg-prospect", "bg-prospect-soft", "text-prospect", "border-prospect",
    "bg-followthrough", "bg-followthrough-soft", "text-followthrough", "border-followthrough",
    "bg-redline", "bg-redline-soft", "text-redline", "border-redline",
  ],
  plugins: [],
};
