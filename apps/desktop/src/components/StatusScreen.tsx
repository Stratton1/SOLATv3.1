import { memo } from "react";
import { DemoChecklist } from "./DemoChecklist";
import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { ExecutionPanel } from "./ExecutionPanel";
import { InfoTip } from "./InfoTip";
import { useAutopilot } from "../hooks/useAutopilot";
import { useFlashOnChange } from "../hooks/useFlashOnChange";
import { useTerminalSignals } from "../hooks/useTerminalSignals";

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
  onStartEngine?: () => void;
  isStartingEngine?: boolean;
}

const HealthCard = memo(function HealthCard({
  health,
  formatUptime,
}: {
  health: HealthData | null;
  formatUptime: (s: number) => string;
}) {
  return (
    <div className="status-card">
      <div className="card-header">
        <span className="card-title">
          Engine Health
          <InfoTip text="Shows whether the Python trading engine is running and responsive. A healthy engine means all services are operational." />
        </span>
        <span className={`card-badge ${health?.status === "healthy" ? "healthy" : ""}`}>
          {health?.status?.toUpperCase() ?? "UNKNOWN"}
        </span>
      </div>
      <div className="card-value num">{formatUptime(health?.uptime_seconds ?? 0)}</div>
      <div className="card-label">Uptime</div>
    </div>
  );
});

const ModeCard = memo(function ModeCard({ config }: { config: ConfigData | null }) {
  return (
    <div className="status-card">
      <div className="card-header">
        <span className="card-title">
          Trading Mode
          <InfoTip text="DEMO mode uses paper trading with simulated fills. LIVE mode sends real orders to IG Markets. Switching to LIVE requires a multi-step confirmation process." />
        </span>
        <span className={`card-badge ${config?.mode === "DEMO" ? "demo" : "live"}`}>
          {config?.mode ?? "\u2014"}
        </span>
      </div>
      <div className="card-value" style={{ fontSize: 24 }}>
        {config?.mode === "DEMO" ? "Paper Trading" : "Live Trading"}
      </div>
      <div className="card-label">
        {config?.ig_configured ? "IG Credentials Configured" : "IG Not Configured"}
      </div>
    </div>
  );
});

const VersionCard = memo(function VersionCard({
  health,
  config,
}: {
  health: HealthData | null;
  config: ConfigData | null;
}) {
  return (
    <div className="status-card">
      <div className="card-header">
        <span className="card-title">
          Engine Version
          <InfoTip text="The version of the SOLAT trading engine. Ensure this matches your desktop app version for compatibility." />
        </span>
      </div>
      <div className="card-value" style={{ fontSize: 24 }}>
        {health?.version ?? "\u2014"}
      </div>
      <div className="card-label">Environment: {config?.env ?? "\u2014"}</div>
    </div>
  );
});

const WsCard = memo(function WsCard({
  wsConnected,
  heartbeatCount,
}: {
  wsConnected: boolean;
  heartbeatCount: number;
}) {
  const flashClass = useFlashOnChange(heartbeatCount);
  return (
    <div className="status-card">
      <div className="card-header">
        <span className="card-title">
          Real-time Connection
          <InfoTip text="WebSocket connection for live data. When connected, you receive real-time heartbeats, quotes, and execution updates from the engine." />
        </span>
        <span className={`card-badge ${wsConnected ? "healthy" : ""}`}>
          {wsConnected ? "CONNECTED" : "DISCONNECTED"}
        </span>
      </div>
      <div className={`card-value num ${flashClass}`}>{heartbeatCount}</div>
      <div className="card-label">Heartbeats Received</div>
    </div>
  );
});

function AutopilotCard() {
  const { state, isLoading, error, enable, disable } = useAutopilot();

  if (isLoading) {
    return (
      <div className="status-card autopilot-card">
        <div className="skeleton skeleton-card" />
      </div>
    );
  }

  return (
    <div className="status-card autopilot-card">
      <div className="card-header">
        <span className="card-title">
          Autopilot
          <InfoTip text="Autopilot automatically runs strategies from your allowlist on incoming bar data. DEMO-only. All signals flow through the risk engine and kill switch." />
        </span>
        <span className={`card-badge ${state?.enabled ? "demo" : ""}`}>
          {state?.enabled ? "ENABLED" : "DISABLED"}
        </span>
      </div>

      <div className="autopilot-metrics">
        <div className="autopilot-metric">
          <span className="autopilot-metric-value num">{state?.combo_count ?? 0}</span>
          <span className="autopilot-metric-label">Combos</span>
        </div>
        <div className="autopilot-metric">
          <span className="autopilot-metric-value num">{state?.cycle_count ?? 0}</span>
          <span className="autopilot-metric-label">Cycles</span>
        </div>
        <div className="autopilot-metric">
          <span className="autopilot-metric-value num">{state?.signals_generated ?? 0}</span>
          <span className="autopilot-metric-label">Signals</span>
        </div>
        <div className="autopilot-metric">
          <span className="autopilot-metric-value num">{state?.intents_routed ?? 0}</span>
          <span className="autopilot-metric-label">Routed</span>
        </div>
      </div>

      <div className="autopilot-toggle">
        <button
          className={`wizard-btn ${state?.enabled ? "" : "primary"}`}
          onClick={state?.enabled ? disable : enable}
        >
          {state?.enabled ? "Disable Autopilot" : "Enable Autopilot"}
        </button>
        <span className="card-badge demo" style={{ marginLeft: 8, fontSize: 10 }}>
          DEMO ONLY
        </span>
      </div>

      {error && <div className="autopilot-error">{error}</div>}

      {state?.blocked_reasons && state.blocked_reasons.length > 0 && (
        <ul className="autopilot-blockers">
          {state.blocked_reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TerminalSignalsCard() {
  const { signals, total, isLoading, error, refetch } = useTerminalSignals({ limit: 20 });

  if (isLoading) {
    return (
      <div className="status-card terminal-signals-card">
        <div className="skeleton skeleton-card" />
      </div>
    );
  }

  return (
    <div className="status-card terminal-signals-card">
      <div className="card-header">
        <span className="card-title">
          Terminal Signals
          <InfoTip text="Recent signals recorded by the execution engine. Shows the latest order intents generated by strategies, including symbol, direction, size, and bot source. Refreshes every 10 seconds." />
        </span>
        <button className="opt-refresh-btn" onClick={refetch}>Refresh</button>
      </div>

      {error && <div className="autopilot-error">{error}</div>}

      {signals.length === 0 ? (
        <div className="terminal-signals-empty">
          No signals recorded yet. Enable Autopilot or use Run Once to generate signals.
        </div>
      ) : (
        <>
          <div className="terminal-signals-summary">
            {total} total signal{total !== 1 ? "s" : ""} recorded
          </div>
          <div className="terminal-signals-table-wrap">
            <table className="terminal-signals-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Size</th>
                  <th>Bot</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, i) => (
                  <tr key={sig.intent_id ?? i}>
                    <td className="mono num">
                      {sig.ts ? new Date(sig.ts).toLocaleTimeString() : "\u2014"}
                    </td>
                    <td className="mono">{sig.symbol ?? "\u2014"}</td>
                    <td className={sig.side === "BUY" ? "positive" : sig.side === "SELL" ? "negative" : ""}>
                      {sig.side ?? "\u2014"}
                    </td>
                    <td className="mono num">{sig.size ?? "\u2014"}</td>
                    <td>{sig.bot ?? "\u2014"}</td>
                    <td className="mono num">
                      {sig.confidence != null ? sig.confidence.toFixed(2) : "\u2014"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export function StatusScreen({
  health,
  config,
  heartbeatCount,
  isLoading,
  error,
  wsConnected,
  onStartEngine,
  isStartingEngine = false,
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
          <div className="error-icon">{"\u26A0"}</div>
          <h2 className="error-title">Engine Connection Failed</h2>
          <p className="error-message">
            Unable to connect to the SOLAT engine. Make sure the Python sidecar is running
            on port 8765.
          </p>
          <p className="error-message" style={{ marginTop: 8, fontSize: 12, opacity: 0.7 }}>
            {error}
          </p>
          {onStartEngine && (
            <button
              className="start-engine-btn"
              onClick={onStartEngine}
              disabled={isStartingEngine}
              style={{ marginTop: 16 }}
            >
              {isStartingEngine ? "Starting Engine..." : "Start Engine"}
            </button>
          )}
        </div>
      </div>
    );
  }

  const formatUptime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
    if (minutes > 0) return `${minutes}m ${secs}s`;
    return `${secs}s`;
  };

  return (
    <div className="status-screen">
      <h2 className="status-title">System Status</h2>

      <div className="status-grid">
        <HealthCard health={health} formatUptime={formatUptime} />
        <ModeCard config={config} />
        <VersionCard health={health} config={config} />
        <WsCard wsConnected={wsConnected} heartbeatCount={heartbeatCount} />
      </div>

      {/* DEMO Setup Checklist */}
      <h2 className="status-title">
        DEMO Setup
        <InfoTip text="Step-by-step checklist to get your first DEMO trade running. Complete steps 1-4 then trigger Run Once." />
      </h2>
      <DemoChecklist />

      {/* Autopilot */}
      <h2 className="status-title">
        Autopilot
        <InfoTip text="Autopilot runs your allowlisted strategies automatically on incoming market data. DEMO-only. All orders pass through the risk engine and kill switch." />
      </h2>
      <AutopilotCard />

      {/* Terminal Signals */}
      <h2 className="status-title">
        Terminal Signals
        <InfoTip text="Recent order intents and signals recorded by the execution engine. Shows all signals generated by autopilot, run-once, and strategy evaluations." />
      </h2>
      <TerminalSignalsCard />

      {/* Configuration Details */}
      <h2 className="status-title">Configuration</h2>
      <div className="status-card">
        <div className="info-row">
          <span className="info-label">Data Directory</span>
          <span className="info-value">{config?.data_dir ?? "\u2014"}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Server Time</span>
          <span className="info-value">
            {health?.time ? new Date(health.time).toLocaleString() : "\u2014"}
          </span>
        </div>
        <div className="info-row">
          <span className="info-label">IG Integration</span>
          <span className="info-value">
            {config?.ig_configured ? "\u2713 Configured" : "\u2717 Not Configured"}
          </span>
        </div>
      </div>

      {/* Execution Control Panel */}
      <h2 className="status-title">
        Execution Control
        <InfoTip text="Connect to IG Markets, arm the execution engine for live signals, or activate the kill switch to halt all trading immediately." />
      </h2>
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
