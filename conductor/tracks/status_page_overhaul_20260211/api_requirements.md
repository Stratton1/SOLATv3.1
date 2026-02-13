# API Requirements: Status Page Overhaul

## 1. System Metrics Enhancement
Currently, `HealthResponse` only returns `status`, `version`, `time`, and `uptime_seconds`. We need to add system resource utilization.

**Endpoint:** `GET /health` or `GET /diagnostics/system`
**Response Addition:**
```json
{
  "system": {
    "cpu_pct": 5.2,
    "memory_usage_mb": 142.5,
    "disk_free_gb": 450.2,
    "process_id": 1234
  }
}
```
**Implementation Note:** Use `psutil` library in the engine.

## 2. Broker Metrics Enhancement
Enhance the existing `/ig/status` endpoint to provide better insight into the broker connection.

**Endpoint:** `GET /ig/status`
**Response Addition:**
```json
{
  "metrics": {
    "last_request_latency_ms": 124,
    "average_latency_ms": 115,
    "session_expiry_ts": "2026-02-12T14:30:00Z",
    "rate_limit_usage_pct": 12.5
  }
}
```

## 3. Risk Gate Detail
Ensure `/execution/gates` provides enough context for the UI to explain *why* a gate is closed.

**Endpoint:** `GET /execution/gates`
**Requirement:** The `GateStatusResponse` should include a `reason` or `metadata` field for each gate that fails evaluation.

## 4. Filtered Log Tail
To support the "High-Priority Event Log" on the dashboard, we need an endpoint to fetch recent logs.

**Endpoint:** `GET /diagnostics/logs`
**Parameters:**
- `level`: `DEBUG|INFO|WARNING|ERROR` (min level, default `INFO`)
- `limit`: `int` (default `50`)
**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2026-02-12T10:00:00Z",
      "level": "ERROR",
      "logger": "solat_engine.execution.router",
      "message": "Order rejected by broker: Insufficient funds",
      "extra": { "symbol": "EURUSD", "size": 1.0 }
    }
  ]
}
```
**Implementation Note:** May require adding a `ListHandler` or similar to the engine's logging setup to keep the last N entries in memory.
