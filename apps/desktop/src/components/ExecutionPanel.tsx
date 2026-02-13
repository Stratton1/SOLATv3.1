import { useState } from "react";
import { useExecutionStatus } from "../hooks/useExecutionStatus";
import { useExecutionMode } from "../hooks/useExecutionMode";
import { useToast } from "../context/ToastContext";
import { InfoTip } from "./InfoTip";
import { formatPnl } from "../lib/format";

interface ExecutionPanelProps {
  igConfigured: boolean;
}

export function ExecutionPanel({ igConfigured }: ExecutionPanelProps) {
  const {
    status,
    isLoading,
    error,
    connect,
    disconnect,
    arm,
    disarm,
    activateKillSwitch,
    resetKillSwitch,
  } = useExecutionStatus();
  const {
    mode: modeFlags,
    setSignalsEnabled,
    setDemoArmEnabled,
  } = useExecutionMode();
  const { showToast } = useToast();

  const [isActioning, setIsActioning] = useState(false);

  const handleConnect = async () => {
    setIsActioning(true);
    try {
      const result = await connect();
      if (result.ok) {
        showToast("Connected to IG successfully", "success");
      } else {
        showToast(result.error || "Connection failed", "error");
      }
    } finally {
      setIsActioning(false);
    }
  };

  const handleDisconnect = async () => {
    setIsActioning(true);
    try {
      await disconnect();
      showToast("Disconnected from IG", "info");
    } finally {
      setIsActioning(false);
    }
  };

  const handleArm = async () => {
    setIsActioning(true);
    try {
      const result = await arm(true);
      if (result.ok) {
        showToast("Execution engine ARMED", "success");
      } else {
        showToast(result.error || "Arming failed", "error");
      }
    } finally {
      setIsActioning(false);
    }
  };

  const handleDisarm = async () => {
    setIsActioning(true);
    try {
      await disarm();
      showToast("Execution engine DISARMED", "info");
    } finally {
      setIsActioning(false);
    }
  };

  const handleKillSwitch = async () => {
    setIsActioning(true);
    try {
      await activateKillSwitch("manual");
      showToast("KILL SWITCH ACTIVATED", "error");
    } finally {
      setIsActioning(false);
    }
  };

  const handleResetKillSwitch = async () => {
    setIsActioning(true);
    try {
      await resetKillSwitch();
      showToast("Kill switch reset", "info");
    } finally {
      setIsActioning(false);
    }
  };

  if (isLoading || !status) {
    return <div className="skeleton" style={{ height: 200 }} />;
  }

  if (error) {
    return <div className="panel-error">{error}</div>;
  }

  return (
    <div className="execution-panel-dense">
      {/* Metrics Row */}
      <div className="autopilot-metrics" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: 12 }}>
        <div className="autopilot-metric">
          <span className="autopilot-metric-value num tabular-nums" style={{ fontSize: 16 }}>{status.open_position_count}</span>
          <span className="autopilot-metric-label">Open Positions</span>
        </div>
        <div className="autopilot-metric">
          <span className={`autopilot-metric-value num tabular-nums ${status.realized_pnl_today >= 0 ? "text-green" : "text-red"}`} style={{ fontSize: 16 }}>
            {formatPnl(status.realized_pnl_today)}
          </span>
          <span className="autopilot-metric-label">PnL Today</span>
        </div>
      </div>

      {/* Connectivity/Mode Indicators */}
      <div className="dense-grid" style={{ marginBottom: 12 }}>
        <div className="dense-row">
          <span className="dense-label">Connected</span>
          <span className={`indicator-dot ${status.connected ? "connected" : ""}`} />
        </div>
        <div className="dense-row">
          <span className="dense-label">Armed</span>
          <span className={`indicator-dot ${status.armed ? "armed" : ""}`} />
        </div>
        <div className="dense-row">
          <span className="dense-label">Kill Switch</span>
          <span className={`indicator-dot ${status.kill_switch_active ? "kill-active" : ""}`} />
        </div>
      </div>

      {/* Control Flags */}
      {modeFlags && (
        <div className="execution-mode-flags" style={{ marginBottom: 12 }}>
          <div className="mode-flag">
            <label className="mode-flag-label">
              <input
                type="checkbox"
                checked={modeFlags.signals_enabled}
                onChange={(e) => setSignalsEnabled(e.target.checked)}
              />
              <span style={{ fontSize: 11 }}>Signals Enabled</span>
              <InfoTip text="When enabled, strategies generate signals on incoming bars." />
            </label>
          </div>
          <div className="mode-flag">
            <label className="mode-flag-label">
              <input
                type="checkbox"
                checked={modeFlags.demo_arm_enabled}
                onChange={(e) => setDemoArmEnabled(e.target.checked)}
                disabled={modeFlags.mode !== "DEMO"}
              />
              <span style={{ fontSize: 11 }}>DEMO Arm</span>
              <InfoTip text="Allow orders in DEMO mode. Required for autopilot execution." />
            </label>
          </div>
        </div>
      )}

      {/* Control Buttons */}
      <div className="execution-controls" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {!status.connected ? (
          <button
            className="wizard-btn primary"
            style={{ gridColumn: "span 2" }}
            onClick={handleConnect}
            disabled={isActioning || !igConfigured}
          >
            {isActioning ? "CONNECTING..." : "CONNECT TO BROKER"}
          </button>
        ) : (
          <>
            <button
              className="wizard-btn"
              onClick={handleDisconnect}
              disabled={isActioning}
            >
              DISCONNECT
            </button>
            
            {!status.armed ? (
              <button
                className="wizard-btn primary"
                onClick={handleArm}
                disabled={isActioning || status.kill_switch_active}
              >
                ARM ENGINE
              </button>
            ) : (
              <button
                className="wizard-btn"
                onClick={handleDisarm}
                disabled={isActioning}
              >
                DISARM
              </button>
            )}
          </>
        )}

        {status.connected && (
          <div style={{ gridColumn: "span 2", marginTop: 4 }}>
            {!status.kill_switch_active ? (
              <button
                className="wizard-btn danger"
                style={{ width: "100%", background: "var(--accent-red)", color: "white", border: "none" }}
                onClick={handleKillSwitch}
                disabled={isActioning}
              >
                KILL TRADING
              </button>
            ) : (
              <button
                className="wizard-btn primary"
                style={{ width: "100%" }}
                onClick={handleResetKillSwitch}
                disabled={isActioning}
              >
                RESET KILL SWITCH
              </button>
            )}
          </div>
        )}
      </div>

      {!igConfigured && !status.connected && (
        <div style={{ fontSize: 10, color: "var(--accent-yellow)", marginTop: 8, textAlign: "center" }}>
          IG credentials not configured in .env
        </div>
      )}
    </div>
  );
}
