import { memo, useState } from "react";
import { DemoChecklist } from "./DemoChecklist";
import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { ExecutionPanel } from "./ExecutionPanel";
import { InfoTip } from "./InfoTip";
import { useAutopilot } from "../hooks/useAutopilot";
import { useFlashOnChange } from "../hooks/useFlashOnChange";
import { useTerminalSignals } from "../hooks/useTerminalSignals";
import { useAllowlist } from "../hooks/useAllowlist";
import { useIgStatus } from "../hooks/useIgStatus";
import { useToast } from "../context/ToastContext";
import { engineClient } from "../lib/engineClient";

// =============================================================================
// Types
// =============================================================================

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

// =============================================================================
// Sub-components
// =============================================================================

const ConnectivityLEDs = memo(function ConnectivityLEDs({
  health,
  igConfigured,
  igAuthenticated,
  wsConnected,
}: {
  health: HealthData | null;
  igConfigured: boolean;
  igAuthenticated: boolean;
  wsConnected: boolean;
}) {
  return (
    <div className="led-group">
      <div className="led-item">
        <div className={`led ${health?.status === "healthy" ? "active" : "error"}`} />
        ENGINE REST
      </div>
      <div className="led-item">
        <div className={`led ${wsConnected ? "active" : "error"}`} />
        WEBSOCKET
      </div>
      <div className="led-item">
        <div className={`led ${igAuthenticated ? "active" : igConfigured ? "warning" : "error"}`} />
        IG BROKER
      </div>
    </div>
  );
});

const ConnectivityCard = memo(function ConnectivityCard({
  health,
  config,
  igAuthenticated,
  heartbeatCount,
  formatUptime,
}: {
  health: HealthData | null;
  config: ConfigData | null;
  igAuthenticated: boolean;
  heartbeatCount: number;
  formatUptime: (s: number) => string;
}) {
  const flashClass = useFlashOnChange(heartbeatCount);

  return (
    <div className="terminal-card">
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          System Connectivity
          <InfoTip text="Core connectivity status for the trading engine and data feeds. Green indicators mean the system is ready for operation." />
        </span>
      </div>
      <div className="terminal-card-body">
        <div className="dense-row">
          <span className="dense-label">Engine REST</span>
          <span className={`dense-value ${health?.status === "healthy" ? "text-green" : "text-red"}`}>
            {health?.status === "healthy" ? "HEALTHY" : "OFFLINE"}
          </span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Uptime</span>
          <span className="dense-value num tabular-nums">{formatUptime(health?.uptime_seconds ?? 0)}</span>
        </div>
        <div className="dense-row">
          <span className="dense-label">WebSocket</span>
          <span className={`dense-value num tabular-nums ${flashClass}`}>{heartbeatCount} HB</span>
        </div>
        <div className="dense-row" style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border-color)" }}>
          <span className="dense-label">IG Configured</span>
          <span className={`dense-value ${config?.ig_configured ? "text-green" : "text-yellow"}`}>
            {config?.ig_configured ? "YES" : "NO"}
          </span>
        </div>
        <div className="dense-row">
          <span className="dense-label">IG Auth</span>
          <span className={`dense-value ${igAuthenticated ? "text-green" : "text-red"}`}>
            {igAuthenticated ? "AUTHENTICATED" : "NOT LOGGED IN"}
          </span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Account Mode</span>
          <span className={`dense-value ${config?.mode === "LIVE" ? "text-red" : "text-green"}`}>
            {config?.mode ?? "\u2014"}
          </span>
        </div>
      </div>
    </div>
  );
});

const ActionPanel = memo(function ActionPanel({
  onStartEngine,
  isStartingEngine,
  engineHealthy,
}: {
  onStartEngine?: () => void;
  isStartingEngine?: boolean;
  engineHealthy: boolean;
}) {
  const [deriving, setDeriving] = useState(false);
  const { showToast } = useToast();

  const handleDerive = async () => {
    if (!engineHealthy) return;
    setDeriving(true);
    try {
      const result = await engineClient.deriveAll();
      if (result.ok) {
        showToast("Derive job started successfully", "success");
      } else {
        showToast(result.message || "Derive failed", "error");
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Derive failed", "error");
    } finally {
      setDeriving(false);
    }
  };

  const handleCopyDiagnostics = async () => {
    try {
      const bundle = await engineClient.getDiagnosticsBundle();
      await navigator.clipboard.writeText(JSON.stringify(bundle, null, 2));
      showToast("Diagnostics copied to clipboard", "success");
    } catch (e) {
      showToast("Failed to copy diagnostics", "error");
    }
  };

  return (
    <div className="terminal-card">
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Quick Actions
          <InfoTip text="Common administrative tasks for engine management. Start the engine if offline, or derive higher timeframe bars from 1m data." />
        </span>
      </div>
      <div className="terminal-card-body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <button
          className="wizard-btn primary"
          onClick={onStartEngine}
          disabled={isStartingEngine || engineHealthy}
        >
          {isStartingEngine ? "Starting..." : engineHealthy ? "Engine Running" : "Start Engine"}
        </button>
        <button
          className="wizard-btn"
          onClick={handleDerive}
          disabled={!engineHealthy || deriving}
        >
          {deriving ? "Deriving..." : "Derive Timeframes"}
        </button>
        <button className="wizard-btn" onClick={handleCopyDiagnostics} disabled={!engineHealthy}>
          Copy Diagnostics
        </button>
      </div>
    </div>
  );
});

function TerminalSignalsTable() {
  const { signals, total, isLoading, error, refetch } = useTerminalSignals({ limit: 50 });

  return (
    <div className="terminal-card" style={{ flex: 1, overflow: "hidden" }}>
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Live Signals
          <InfoTip text="Real-time order intents generated by the engine strategies. Shows direction, size, and confidence for recent evaluations." />
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="dense-label tabular-nums" style={{ fontSize: 10 }}>{total} TOTAL</span>
          <button className="opt-refresh-btn" onClick={refetch} disabled={isLoading}>
            {isLoading ? "..." : "REFRESH"}
          </button>
        </div>
      </div>
      <div className="terminal-card-body" style={{ padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {error ? (
          <div style={{ padding: 20, color: "var(--accent-red)", fontSize: 12 }}>{error}</div>
        ) : isLoading && signals.length === 0 ? (
          <div className="skeleton" style={{ height: "100%" }} />
        ) : (
          <div className="scroll-area">
            <table className="terminal-signals-table dense">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Size</th>
                  <th>Bot</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, i) => (
                  <tr key={sig.intent_id ?? i}>
                    <td className="mono num tabular-nums">
                      {sig.ts ? new Date(sig.ts).toLocaleTimeString([], { hour12: false }) : "\u2014"}
                    </td>
                    <td className="mono" style={{ fontWeight: 600 }}>{sig.symbol ?? "\u2014"}</td>
                    <td className={sig.side === "BUY" ? "positive" : sig.side === "SELL" ? "negative" : ""}>
                      {sig.side ?? "\u2014"}
                    </td>
                    <td className="mono num tabular-nums">{sig.size ?? "\u2014"}</td>
                    <td style={{ fontSize: 10, color: "var(--text-secondary)" }}>{sig.bot ?? "\u2014"}</td>
                  </tr>
                ))}
                {signals.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: "center", padding: 20, color: "var(--text-muted)" }}>
                      NO SIGNALS RECORDED
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function AutopilotStatus() {
  const { state, enable, disable } = useAutopilot();

  return (
    <div className="terminal-card">
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Autopilot
          <InfoTip text="Automated strategy execution on incoming bar data. When enabled, Autopilot will scan allowlisted symbols and route trades to the risk engine. DEMO ONLY." />
        </span>
        <span className={`card-badge ${state?.enabled ? "demo" : ""}`}>
          {state?.enabled ? "ENABLED" : "DISABLED"}
        </span>
      </div>
      <div className="terminal-card-body">
        <div className="autopilot-metrics" style={{ gridTemplateColumns: "repeat(4, 1fr)", marginBottom: 12 }}>
          <div className="autopilot-metric">
            <span className="autopilot-metric-value num tabular-nums" style={{ fontSize: 16 }}>{state?.combo_count ?? 0}</span>
            <span className="autopilot-metric-label" style={{ fontSize: 9 }}>Combos</span>
          </div>
          <div className="autopilot-metric">
            <span className="autopilot-metric-value num tabular-nums" style={{ fontSize: 16 }}>{state?.cycle_count ?? 0}</span>
            <span className="autopilot-metric-label" style={{ fontSize: 9 }}>Cycles</span>
          </div>
          <div className="autopilot-metric">
            <span className="autopilot-metric-value num tabular-nums" style={{ fontSize: 16 }}>{state?.signals_generated ?? 0}</span>
            <span className="autopilot-metric-label" style={{ fontSize: 9 }}>Signals</span>
          </div>
          <div className="autopilot-metric">
            <span className="autopilot-metric-value num tabular-nums" style={{ fontSize: 16 }}>{state?.intents_routed ?? 0}</span>
            <span className="autopilot-metric-label" style={{ fontSize: 9 }}>Routed</span>
          </div>
        </div>
        <button
          className={`wizard-btn ${state?.enabled ? "" : "primary"}`}
          onClick={state?.enabled ? disable : enable}
          style={{ width: "100%" }}
        >
          {state?.enabled ? "Disable Autopilot" : "Enable Autopilot"}
        </button>
      </div>
    </div>
  );
}

function AllowlistGrid() {
  const { grouped, isLoading, error } = useAllowlist();

  return (
    <div className="terminal-card" style={{ flex: 1, overflow: "hidden" }}>
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Trading Allowlist
          <InfoTip text="Eligible symbol/bot/timeframe combinations for execution. These are sourced from your latest Walk-Forward optimization runs." />
        </span>
      </div>
      <div className="terminal-card-body">
        <div className="scroll-area">
          {isLoading ? (
            <div className="skeleton" style={{ height: 100 }} />
          ) : error ? (
            <div style={{ color: "var(--accent-red)", fontSize: 11 }}>{error}</div>
          ) : grouped.length === 0 ? (
            <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: 11, padding: 20 }}>
              NO ACTIVE TRADING COMBOS
            </div>
          ) : (
            <div className="allowlist-grouped-grid">
              {grouped.map((group) => (
                <div key={group.symbol} className="allowlist-symbol-group">
                  <div className="allowlist-symbol-header">{group.symbol}</div>
                  <div className="allowlist-symbol-entries">
                    {group.bots.map((entry) => (
                      <div key={entry.combo_id} className={`allowlist-entry-tag ${entry.enabled ? "active" : "disabled"}`}>
                        <span className="entry-bot">{entry.bot}</span>
                        <span className="entry-tf">{entry.timeframe}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

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
  const { data: igStatus } = useIgStatus();

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
          <h2 className="error-title">Engine Offline</h2>
          <p className="error-message">{error}</p>
          {onStartEngine && (
            <button
              className="wizard-btn primary"
              onClick={onStartEngine}
              disabled={isStartingEngine}
              style={{ marginTop: 16 }}
            >
              {isStartingEngine ? "Starting..." : "Start Engine"}
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
    <div className="status-dashboard">
      {/* Header Area */}
      <header className="status-dashboard-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h2 style={{ fontSize: 12, fontWeight: 800, color: "var(--text-primary)", letterSpacing: "0.1em" }}>MISSION CONTROL</h2>
          <span className="card-badge" style={{ background: "var(--bg-tertiary)", color: "var(--text-secondary)", fontSize: 9 }}>
            {config?.env?.toUpperCase()}
          </span>
        </div>
        <ConnectivityLEDs
          health={health}
          igConfigured={config?.ig_configured ?? false}
          igAuthenticated={igStatus?.authenticated ?? false}
          wsConnected={wsConnected}
        />
      </header>

      {/* Left Column: Connectivity & Actions */}
      <aside className="status-dashboard-left">
        <ConnectivityCard
          health={health}
          config={config}
          igAuthenticated={igStatus?.authenticated ?? false}
          heartbeatCount={heartbeatCount}
          formatUptime={formatUptime}
        />
        <ActionPanel
          onStartEngine={onStartEngine}
          isStartingEngine={isStartingEngine}
          engineHealthy={health?.status === "healthy"}
        />
        <div className="terminal-card" style={{ flex: 1 }}>
          <div className="terminal-card-header">
            <span className="terminal-card-title">
              Execution Control
              <InfoTip text="Live execution controls. Arm the engine to begin trading live signals, or use the Kill Switch to stop all activity instantly." />
            </span>
          </div>
          <div className="terminal-card-body">
            <div className="scroll-area">
              <ExecutionPanel igConfigured={config?.ig_configured ?? false} />
            </div>
          </div>
        </div>
      </aside>

      {/* Middle Column: Signals & Autopilot */}
      <main className="status-dashboard-mid">
        <TerminalSignalsTable />
        <AllowlistGrid />
        <AutopilotStatus />
      </main>

      {/* Right Column: Checklist & Diagnostics */}
      <aside className="status-dashboard-right">
        <div className="terminal-card">
          <div className="terminal-card-header">
            <span className="terminal-card-title">
              DEMO Setup Checklist
              <InfoTip text="Interactive guide to preparing the system for its first automated trade. Complete all items before enabling Autopilot." />
            </span>
          </div>
          <div className="terminal-card-body">
            <div className="scroll-area">
              <DemoChecklist />
            </div>
          </div>
        </div>
        <div className="terminal-card" style={{ flex: 1 }}>
          <div className="terminal-card-header">
            <span className="terminal-card-title">
              System Diagnostics
              <InfoTip text="Detailed internal state and event logs. Use for troubleshooting engine or data feed issues." />
            </span>
          </div>
          <div className="terminal-card-body" style={{ padding: 0 }}>
            <div className="scroll-area">
              <DiagnosticsPanel />
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
