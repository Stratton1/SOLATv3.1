# Design: Status Page Overhaul

## Goals
-   Increase transparency of engine internals.
-   Provide actionable info on why execution might be blocked (Risk Gates).
-   Improve visual hierarchy to prioritize critical safety info.

## 1. Component Architecture

### A. Mission Control Header (Unified)
A single row at the top replacing the multiple LEDs.
-   **Live/Demo Badge:** Large and prominent.
-   **Kill Switch Status:** Toggle with clear "ARMED" (Red) vs "SAFE" (Green) states.
-   **Global Health Score:** A single percentage or status based on all sub-systems.

### B. Grid Section: Infrastructure & Safety (Col 1)
-   **System Health Card:**
    -   CPU Usage (%)
    -   Memory Usage (MB)
    -   Disk Free (GB) -> Crucial for Parquet logging.
-   **Risk Gate Monitor:**
    -   A list/grid of all safety gates (e.g., `MaxExposure`, `DailyLoss`, `TradeFreq`).
    -   Visual indicator for each: `PASSED` (Green) or `BLOCKED` (Red).
-   **Broker Connectivity:**
    -   REST Latency (ms)
    -   Session TTL (time until re-auth needed)
    -   Rate Limit Bucket usage (%)

### C. Grid Section: Trading Activity (Col 2)
-   **Live Signal Feed:** Compact table of the last 5-10 signals.
-   **Autopilot Pulse:**
    -   Session runtime.
    -   Efficiency metrics (e.g., signals per hour).
    -   Current scanning status (Idle vs Computing).
-   **Allowlist Status:**
    -   Total active combos.
    -   Quick link to Allowlist management.

### D. Grid Section: Verification & Logs (Col 3)
-   **Setup Checklist:** (Retain current DemoChecklist but styled to match).
-   **High-Priority Event Log:**
    -   Filtered view of `solat_engine.logging` for `WARNING` and `ERROR` levels.
    -   Click to expand/copy full traceback.

## 2. Data Requirements

### Engine API Changes
1.  **`GET /health`**
    -   Add `system`: `{ cpu_pct: float, memory_usage_mb: float, disk_free_gb: float }`
2.  **`GET /broker/status`**
    -   Add `metrics`: `{ latency_ms: int, session_expiry_ts: str, rate_limit_usage: float }`
3.  **`GET /execution/gates`**
    -   Ensure detailed metadata for each gate's current evaluation.

### Frontend Hook Changes
1.  **`useEngineHealth`**: Extend to capture system metrics.
2.  **`useBrokerStatus`**: New hook to poll enhanced broker metrics.
3.  **`useRiskGates`**: New hook to aggregate gate statuses for the dashboard.
