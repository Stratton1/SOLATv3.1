/**
 * Design system tokens for SOLAT Trading Terminal.
 *
 * Professional light theme with trading-grade color semantics.
 * All tokens are exposed as CSS custom properties in styles.css.
 */

// =============================================================================
// Color Tokens
// =============================================================================

export const colors = {
  // Backgrounds
  bgApp: "#f0f2f5",
  bgPrimary: "#ffffff",
  bgSecondary: "#f0f2f5",
  bgTertiary: "#e8ebf0",
  bgCard: "#ffffff",
  bgCardHover: "#f5f7fa",
  bgMuted: "#e8ebf0",
  bgInset: "#ebedf2",

  // Text
  textPrimary: "#1a1d28",
  textSecondary: "#5f6775",
  textMuted: "#8b919e",
  textInverse: "#ffffff",

  // Borders
  borderDefault: "#d5d9e0",
  borderLight: "#e5e8ed",
  borderFocus: "#3d8bfd",

  // Accents — Trading
  buyGreen: "#00d68f",
  buyGreenBg: "rgba(0, 214, 143, 0.10)",
  sellRed: "#f45b69",
  sellRedBg: "rgba(244, 91, 105, 0.10)",

  // Accents — UI
  accentBlue: "#3d8bfd",
  accentBlueBg: "rgba(61, 139, 253, 0.10)",
  accentYellow: "#f7b955",
  accentYellowBg: "rgba(247, 185, 85, 0.10)",
  accentPurple: "#a78bfa",
  accentPurpleBg: "rgba(167, 139, 250, 0.10)",

  // Live mode warning
  liveRed: "#f45b69",
  liveRedBg: "rgba(244, 91, 105, 0.15)",

  // Chart
  chartBg: "#ffffff",
  chartGrid: "#e8ebf0",
  chartText: "#5f6775",
  chartBorder: "#d5d9e0",
  chartCrosshair: "#8b919e",
  chartCrosshairLabel: "#e8ebf0",
  candleUp: "#00d68f",
  candleDown: "#f45b69",

  // Shadows
  shadowSm: "0 1px 2px rgba(0, 0, 0, 0.06)",
  shadowMd: "0 2px 8px rgba(0, 0, 0, 0.08)",
  shadowLg: "0 4px 16px rgba(0, 0, 0, 0.12)",

  // Overlay line colors (for chart indicators — light-theme optimized)
  overlayEma: ["#2563eb", "#d97706", "#7c3aed", "#059669"],
  overlaySma: ["#0891b2", "#db2777", "#ca8a04", "#059669"],
  overlayBollinger: ["#7a8290", "#7a8290", "#7a8290"],
  overlayIchimoku: ["#059669", "#e11d48", "#d97706", "#7a8290", "#7c3aed"],
  overlayRsi: ["#7c3aed"],
  overlayMacd: ["#2563eb", "#e11d48", "#059669"],
  overlayStoch: ["#2563eb", "#d97706"],
  overlayAtr: ["#7a8290"],
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
  sm: "3px",
  md: "5px",
  lg: "6px",
  xl: "8px",
  full: "9999px",
} as const;

// =============================================================================
// Typography
// =============================================================================

export const fonts = {
  sans: "'Geist', -apple-system, BlinkMacSystemFont, sans-serif",
  mono: "'JetBrains Mono', 'SF Mono', Monaco, monospace",
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
  trend: { bg: "rgba(0, 214, 143, 0.10)", text: "#00d68f" },
  momentum: { bg: "rgba(61, 139, 253, 0.10)", text: "#3d8bfd" },
  reversal: { bg: "rgba(247, 185, 85, 0.10)", text: "#f7b955" },
  breakout: { bg: "rgba(167, 139, 250, 0.10)", text: "#a78bfa" },
} as const;
