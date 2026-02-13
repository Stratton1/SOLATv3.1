# Analysis: Existing Status Page Components

## Current State
The Status Page (Mission Control) is a multi-column dashboard providing a high-level overview of the engine's health and operational state.

### Core Components
1.  **ConnectivityLEDs (Header):**
    -   Visual indicators (Green/Red/Yellow) for Engine REST, WebSocket, and IG Broker.
2.  **ConnectivityCard (Left Col):**
    -   Rest Health (Healthy/Offline)
    -   Uptime (formatted duration)
    -   WebSocket Heartbeats (live count)
    -   IG Configuration Status (Yes/No)
    -   IG Auth Status (Authenticated/Not Logged In)
    -   Account Mode (DEMO/LIVE)
3.  **ActionPanel (Left Col):**
    -   Start Engine button
    -   Derive Timeframes button
    -   Copy Diagnostics button
4.  **ExecutionControl (Left Col):**
    -   Arm/Kill Switch (wraps `ExecutionPanel`)
5.  **TerminalSignalsTable (Mid Col):**
    -   Recent signals (Time, Symbol, Side, Size, Bot)
    -   Total count
    -   Refresh capability
6.  **AllowlistGrid (Mid Col):**
    -   Active trading combinations grouped by symbol
7.  **AutopilotStatus (Mid Col):**
    -   Metrics (Combos, Cycles, Signals, Routed)
    -   Enable/Disable toggle
8.  **DemoChecklist (Right Col):**
    -   Step-by-step guide for initial setup
9.  **DiagnosticsPanel (Right Col):**
    -   Event logs and internal diagnostics

## Observed Limitations
-   **Static Data:** Most "health" data is basic (REST ok, uptime).
-   **Lack of System Metrics:** No info on CPU, Memory, or Disk usage (Engine side).
-   **Broker Depth:** No info on broker latency or session time remaining.
-   **Visual Noise:** The screen is very dense with many small cards.
-   **Mobile/Responsive:** The layout is fixed/dense for desktop, which is fine but could be more modular.

## Opportunities for Overhaul
-   **Consolidated Health:** A single "System Health" component that includes system resources (CPU/Mem/Disk).
-   **Active Monitoring:** Add a "latency" indicator for the broker REST connection.
-   **Enhanced Diagnostics:** Filterable logs or "Critical Errors" summary.
-   **Safety Visualization:** More prominent display of "Risk Gates" status.
