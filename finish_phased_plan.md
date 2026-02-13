# SOLAT v3.1 Frontend Overhaul & Completion Plan

**Status:** Draft / Specification
**Target:** Pro-grade Trading Terminal
**Date:** February 13, 2026

## Executive Summary

This plan outlines the definitive roadmap to elevate the SOLAT v3.1 frontend from a functional prototype to a professional-grade algorithmic trading terminal. The focus is on **complete functionality**, **visual density**, and **mission-critical reliability**.

**Strategic Philosophy:**
1.  **Trust through Visibility:** Every background process (sync, signal, risk check) must have a visual representation.
2.  **Actionability:** Every screen must allow immediate action, not just passive viewing.
3.  **Risk First:** Risk controls are ubiquitous, not hidden in settings.

---

## Phase 1: Foundation & Navigation (The "Shell")

**Objective:** Create a responsive, persistent, and professional application shell.

### 1.1 Navigation & Layout
*   **Action:** Implement a sidebar navigation with collapsible groups (Analysis, Execution, System).
*   **Feature:** **Command Palette (`Cmd+K`)** overhaul.
    *   *Current:* Basic navigation.
    *   *New:* Action-oriented commands.
        *   `> Buy EURUSD 1 Lot` (Opens pre-filled ticket)
        *   `> Close All Positions` (Triggers kill switch modal)
        *   `> Theme: Matrix` (Switches CSS variables)
        *   `> Export Blotter CSV`
*   **Feature:** **System Status Strip (Footer)** overhaul.
    *   *Add:* Real-time "Heartbeat" pulse for Engine and Broker connections.
    *   *Add:* Global "Sync Progress" bar (hidden when idle) for data operations.
    *   *Add:* "latency" ms display next to connection status.

### 1.2 Notifications & Feedback
*   **Feature:** **Toast System 2.0**.
    *   *Requirement:* Stackable, dismissible, varying durations.
    *   *Types:*
        *   `Success`: "Order Filled: BUY 1 EURUSD @ 1.0500" (Green)
        *   `Warning`: "Margin Utilization > 70%" (Yellow)
        *   `Error`: "IG API: Rate Limit Exceeded" (Red, persistent until dismissed)
*   **Feature:** **Notification Center**.
    *   A bell icon in the header opening a drawer of past notifications, grouped by session.

---

## Phase 2: The Trading Core (Terminal & Charts)

**Objective:** Make the chart the primary workspace for decision-making.

### 2.1 Multi-Chart Grid
*   **Action:** Replace single chart view with a CSS Grid layout system.
*   **Features:**
    *   **Layouts:** Presets for 1x1, 2x1 (Vertical/Horizontal), 2x2, 1+3 (Main + 3 small).
    *   **Symbol Sync:** Checkbox to link Symbol across all charts.
    *   **Crosshair Sync:** Hovering time `T` on Chart A shows cursor at `T` on Chart B.

### 2.2 Interactive Charting
*   **Action:** Enhance `CandleChart.tsx` (Lightweight Charts).
*   **Features:**
    *   **On-Chart Trading:**
        *   "Quick Trade" buttons (Buy/Sell) in top-left corner of chart.
        *   Visual lines for Open Orders (Entry, SL, TP).
        *   *Interactive:* Dragging SL line updates the order (via `PUT /execution/orders/{id}`).
    *   **Drawing Toolbar:**
        *   Simple vertical toolbar: Trendline, Horizontal Ray, Fibonacci, Rect.
    *   **Event Flags:**
        *   Vertical dashed lines for "News Events" or "Strategy Signals" with hover tooltips.

### 2.3 Order Entry (DOM)
*   **Action:** Create `OrderTicket.tsx`.
*   **Features:**
    *   **Depth of Market (DOM):** Visual ladder of price (simulated if L2 data unavailable, or just Bid/Ask spread visualization).
    *   **Smart Size:** Input field for "Risk %" that auto-calculates Lot Size based on SL distance.
    *   **Validation:** "Place Order" button disabled if size > limits or margin insufficient.

---

## Phase 3: Data & Strategy Intelligence

**Objective:** Visualize the invisible quality of data and strategy logic.

### 3.1 Data Health Dashboard
*   **Action:** Overhaul `Library` tab.
*   **Features:**
    *   **Coverage Visualizer:** A horizontal bar chart for each symbol.
        *   Green = Continuous Data.
        *   Red = Missing/Gap.
        *   Grey = No Data.
    *   **Gap Repair:** A "Heal" button that dispatches specific date-range fetch tasks for red segments.

### 3.2 Backtest Intelligence
*   **Action:** Upgrade `BacktestsScreen.tsx`.
*   **Features:**
    *   **Compare Mode:** Select multiple backtest IDs -> Overlay Equity Curves on one chart.
    *   **Heatmaps:** "Day of Week" vs "Hour of Day" P&L heatmap.
    *   **Underwater Plot:** dedicated chart for Drawdown %.

---

## Phase 4: Execution, Risk & Audit

**Objective:** Total transparency and "What-If" analysis.

### 4.1 Blotter Evolution
*   **Action:** Enhance `BlotterScreen.tsx`.
*   **Features:**
    *   **Advanced Filter:** "Filter by..." bar supports logic: `Symbol=EURUSD AND PnL < 0`.
    *   **Row Expansion:** Clicking a "Fill" row expands to show the "Signal" event that caused it (Audit Trail).
    *   **Visual Lifecycle:** A generic "Trace" view showing `Signal -> Intent -> Order -> Fill` with timestamps for latency analysis.

### 4.2 Risk Sandbox & Stress Testing
*   **Context:** While the Blotter shows *history*, the Sandbox shows *potential future*.
*   **Action:** Create `RiskSandbox.tsx` (integrated into Blotter or as a sub-tab).
*   **Features:**
    *   **"Stress Test Open Positions":**
        *   Button in Blotter: "Run Stress Test".
        *   Opens modal/panel: "What if market moves -1%, -5%, -10%?".
        *   Result: Projected P&L impact table for all open positions.
    *   **"Pre-Trade Simulation":**
        *   Input: "Buy 10 Lots EURUSD".
        *   Output: "Margin required: $X. New Leverage: Y. Liquidation Price: Z."

### 4.3 Dashboard 2.0 (Mission Control)
*   **Action:** Redesign `DashboardScreen.tsx`.
*   **Features:**
    *   **Live Ticker:** Scrolling tape of watched symbols.
    *   **Account Gauge:** Radial gauge for Margin Level.
    *   **News Widget:** Integration of an RSS feed for economic calendar.

---

## Implementation Checklist

### Phase 1: Shell
- [ ] `CommandPalette.tsx`: Add action execution logic.
- [ ] `ToastContext.tsx`: Implement stacking and variants.
- [ ] `StatusStrip.tsx`: Add latency and sync progress.

### Phase 2: Core
- [ ] `TerminalScreen.tsx`: Implement Grid Layout state.
- [ ] `CandleChart.tsx`: Add order line rendering and interaction.
- [ ] `OrderTicket.tsx`: Build smart sizing logic.

### Phase 3: Intelligence
- [ ] `LibraryScreen.tsx`: Implement visual coverage bars.
- [ ] `BacktestAnalytics.tsx`: Build comparative charting.

### Phase 4: Risk
- [ ] `RiskSandbox.tsx`: Implement "Stress Test" logic (client-side calculation).
- [ ] `BlotterScreen.tsx`: Add Row Expansion for audit trail.

---

**Definition of Done:**
The frontend is considered "v3.1 Complete" when a user can:
1.  **Sync data** and see visual confirmation of quality.
2.  **Backtest** a strategy and compare it visually against another.
3.  **Execute** a trade from the chart with drag-and-drop SL.
4.  **Monitor** the trade in the Blotter.
5.  **Stress Test** the open position against a 5% market crash.
6.  **Close** the position via Command Palette.
