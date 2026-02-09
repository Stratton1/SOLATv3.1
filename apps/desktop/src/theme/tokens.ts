/**
 * Design system tokens for SOLAT Trading Terminal.
 *
 * Light-first theme with trading-grade color semantics.
 * All tokens are exposed as CSS custom properties in styles.css.
 */

// =============================================================================
// Color Tokens
// =============================================================================

export const colors = {
  // Backgrounds
  bgApp: "#f5f6f8",
  bgCard: "#ffffff",
  bgCardHover: "#fafbfc",
  bgMuted: "#eef0f4",
  bgInset: "#e8eaef",

  // Text
  textPrimary: "#1a1d23",
  textSecondary: "#5c6370",
  textMuted: "#9da5b4",
  textInverse: "#ffffff",

  // Borders
  borderDefault: "#dfe1e6",
  borderLight: "#eceef2",
  borderFocus: "#4c8bf5",

  // Accents — Trading
  buyGreen: "#16a34a",
  buyGreenBg: "rgba(22, 163, 74, 0.08)",
  sellRed: "#dc2626",
  sellRedBg: "rgba(220, 38, 38, 0.08)",

  // Accents — UI
  accentBlue: "#2563eb",
  accentBlueBg: "rgba(37, 99, 235, 0.08)",
  accentYellow: "#d97706",
  accentYellowBg: "rgba(217, 119, 6, 0.08)",
  accentPurple: "#7c3aed",
  accentPurpleBg: "rgba(124, 58, 237, 0.08)",

  // Live mode warning
  liveRed: "#dc2626",
  liveRedBg: "rgba(220, 38, 38, 0.12)",

  // Chart
  chartBg: "#ffffff",
  chartGrid: "#f0f1f3",
  chartText: "#5c6370",
  chartCrosshair: "#9da5b4",
  chartCrosshairLabel: "#eef0f4",
  candleUp: "#16a34a",
  candleDown: "#dc2626",

  // Shadows
  shadowSm: "0 1px 2px rgba(0, 0, 0, 0.06)",
  shadowMd: "0 2px 8px rgba(0, 0, 0, 0.08)",
  shadowLg: "0 4px 16px rgba(0, 0, 0, 0.1)",

  // Overlay line colors (for chart indicators)
  overlayEma: ["#2563eb", "#d97706", "#7c3aed", "#16a34a"],
  overlaySma: ["#0891b2", "#db2777", "#ca8a04", "#059669"],
  overlayBollinger: ["#6b7280", "#6b7280", "#6b7280"],
  overlayIchimoku: ["#16a34a", "#dc2626", "#d97706", "#9da5b4", "#a78bfa"],
  overlayRsi: ["#7c3aed"],
  overlayMacd: ["#2563eb", "#dc2626", "#16a34a"],
  overlayStoch: ["#2563eb", "#d97706"],
  overlayAtr: ["#6b7280"],
} as const;

// =============================================================================
// Spacing
// =============================================================================

export const spacing = {
  xs: "4px",
  sm: "8px",
  md: "12px",
  lg: "16px",
  xl: "20px",
  xxl: "24px",
} as const;

// =============================================================================
// Radius
// =============================================================================

export const radius = {
  sm: "4px",
  md: "6px",
  lg: "8px",
  xl: "12px",
  full: "9999px",
} as const;

// =============================================================================
// Typography
// =============================================================================

export const fonts = {
  sans: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  mono: '"SF Mono", Monaco, "Cascadia Code", "Fira Code", monospace',
} as const;

export const fontSizes = {
  xs: "10px",
  sm: "11px",
  base: "13px",
  md: "14px",
  lg: "16px",
  xl: "18px",
  xxl: "24px",
} as const;

// =============================================================================
// Category Colors (Elite 8)
// =============================================================================

export const categoryColors = {
  trend: { bg: "rgba(22, 163, 74, 0.1)", text: "#16a34a" },
  momentum: { bg: "rgba(37, 99, 235, 0.1)", text: "#2563eb" },
  reversal: { bg: "rgba(217, 119, 6, 0.1)", text: "#d97706" },
  breakout: { bg: "rgba(124, 58, 237, 0.1)", text: "#7c3aed" },
} as const;
