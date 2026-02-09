import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { ExecutionPanel } from "./ExecutionPanel";

interface HealthData {
  status: string;
  version: string;
  time: string;
  uptime_seconds: number;
}

interface ConfigData {
  mode: string;
  env: string;
  data_dir: string;
  app_env: string;
  ig_configured: boolean;
}

interface StatusScreenProps {
  health: HealthData | null;
  config: ConfigData | null;
  heartbeatCount: number;
  isLoading: boolean;
  error: string | null;
  wsConnected: boolean;
}

export function StatusScreen({
  health,
  config,
  heartbeatCount,
  isLoading,
  error,
  wsConnected,
}: StatusScreenProps) {
  if (isLoading) {
    return (
      <div className="status-screen">
        <div className="loading-container">
          <div className="loading-spinner" />
          <p className="loading-text">Starting SOLAT Engine...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="status-screen">
        <div className="error-container">
          <div className="error-icon">⚠</div>
          <h2 className="error-title">Engine Connection Failed</h2>
          <p className="error-message">
            Unable to connect to the SOLAT engine. Make sure the Python sidecar is running
            on port 8765.
          </p>
          <p className="error-message" style={{ marginTop: 8, fontSize: 12, opacity: 0.7 }}>
            {error}
          </p>
        </div>
      </div>
    );
  }

  const formatUptime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
  };

  return (
    <div className="status-screen">
      <h2 className="status-title">System Status</h2>

      <div className="status-grid">
        {/* Health Card */}
        <div className="status-card">
          <div className="card-header">
            <span className="card-title">Engine Health</span>
            <span className={`card-badge ${health?.status === "healthy" ? "healthy" : ""}`}>
              {health?.status?.toUpperCase() ?? "UNKNOWN"}
            </span>
          </div>
          <div className="card-value">{formatUptime(health?.uptime_seconds ?? 0)}</div>
          <div className="card-label">Uptime</div>
        </div>

        {/* Mode Card */}
        <div className="status-card">
          <div className="card-header">
            <span className="card-title">Trading Mode</span>
            <span
              className={`card-badge ${config?.mode === "DEMO" ? "demo" : "live"}`}
            >
              {config?.mode ?? "—"}
            </span>
          </div>
          <div className="card-value" style={{ fontSize: 24 }}>
            {config?.mode === "DEMO" ? "Paper Trading" : "Live Trading"}
          </div>
          <div className="card-label">
            {config?.ig_configured ? "IG Credentials Configured" : "IG Not Configured"}
          </div>
        </div>

        {/* Version Card */}
        <div className="status-card">
          <div className="card-header">
            <span className="card-title">Engine Version</span>
          </div>
          <div className="card-value" style={{ fontSize: 24 }}>
            {health?.version ?? "—"}
          </div>
          <div className="card-label">Environment: {config?.env ?? "—"}</div>
        </div>

        {/* WebSocket Card */}
        <div className="status-card">
          <div className="card-header">
            <span className="card-title">Real-time Connection</span>
            <span className={`card-badge ${wsConnected ? "healthy" : ""}`}>
              {wsConnected ? "CONNECTED" : "DISCONNECTED"}
            </span>
          </div>
          <div className="card-value">{heartbeatCount}</div>
          <div className="card-label">Heartbeats Received</div>
        </div>
      </div>

      {/* Configuration Details */}
      <h2 className="status-title">Configuration</h2>
      <div className="status-card">
        <div className="info-row">
          <span className="info-label">Data Directory</span>
          <span className="info-value">{config?.data_dir ?? "—"}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Server Time</span>
          <span className="info-value">
            {health?.time ? new Date(health.time).toLocaleString() : "—"}
          </span>
        </div>
        <div className="info-row">
          <span className="info-label">IG Integration</span>
          <span className="info-value">
            {config?.ig_configured ? "✓ Configured" : "✗ Not Configured"}
          </span>
        </div>
      </div>

      {/* Execution Control Panel */}
      <h2 className="status-title">Execution Control</h2>
      <ExecutionPanel igConfigured={config?.ig_configured ?? false} />

      {/* WebSocket Heartbeat Display */}
      <div className="ws-section">
        <div className="ws-indicator">
          <span className={`ws-dot ${wsConnected ? "" : "disconnected"}`} />
          WebSocket {wsConnected ? "Connected" : "Disconnected"}
        </div>
        <div className="heartbeat-display">{heartbeatCount}</div>
        <div className="heartbeat-label">Heartbeat Counter</div>
      </div>

      {/* Diagnostics Panel (collapsed by default) */}
      <h2 className="status-title">System Diagnostics</h2>
      <DiagnosticsPanel />
    </div>
  );
}
