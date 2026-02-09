import { useState } from "react";
import { useExecutionStatus } from "../hooks/useExecutionStatus";

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

  const [actionError, setActionError] = useState<string | null>(null);
  const [isActioning, setIsActioning] = useState(false);

  const handleConnect = async () => {
    setActionError(null);
    setIsActioning(true);
    const result = await connect();
    if (!result.ok) {
      setActionError(result.error || "Connection failed");
    }
    setIsActioning(false);
  };

  const handleDisconnect = async () => {
    setActionError(null);
    setIsActioning(true);
    await disconnect();
    setIsActioning(false);
  };

  const handleArm = async () => {
    setActionError(null);
    setIsActioning(true);
    const result = await arm(true);
    if (!result.ok) {
      setActionError(result.error || "Arm failed");
    }
    setIsActioning(false);
  };

  const handleDisarm = async () => {
    setActionError(null);
    setIsActioning(true);
    await disarm();
    setIsActioning(false);
  };

  const handleKillSwitch = async () => {
    setActionError(null);
    setIsActioning(true);
    await activateKillSwitch("manual");
    setIsActioning(false);
  };

  const handleResetKillSwitch = async () => {
    setActionError(null);
    setIsActioning(true);
    await resetKillSwitch();
    setIsActioning(false);
  };

  if (isLoading || !status) {
    return (
      <div className="execution-panel">
        <h3 className="panel-title">Live Execution</h3>
        <div className="panel-loading">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="execution-panel">
        <h3 className="panel-title">Live Execution</h3>
        <div className="panel-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="execution-panel">
      <h3 className="panel-title">Live Execution</h3>

      {/* Status Indicators */}
      <div className="execution-status-grid">
        <div className="execution-indicator">
          <span className="indicator-label">Mode</span>
          <span className={`indicator-value mode-${status.mode.toLowerCase()}`}>
            {status.mode}
          </span>
        </div>
        <div className="execution-indicator">
          <span className="indicator-label">Connected</span>
          <span className={`indicator-dot ${status.connected ? "connected" : ""}`} />
        </div>
        <div className="execution-indicator">
          <span className="indicator-label">Armed</span>
          <span className={`indicator-dot ${status.armed ? "armed" : ""}`} />
        </div>
        <div className="execution-indicator">
          <span className="indicator-label">Kill Switch</span>
          <span className={`indicator-dot ${status.kill_switch_active ? "kill-active" : ""}`} />
        </div>
      </div>

      {/* Position Count */}
      <div className="execution-positions">
        <div className="position-count">
          <span className="count-value">{status.open_position_count}</span>
          <span className="count-label">Open Positions</span>
        </div>
        {status.account_balance !== null && (
          <div className="account-balance">
            <span className="balance-value">
              {status.account_balance.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
            <span className="balance-label">Balance</span>
          </div>
        )}
        <div className="pnl-today">
          <span className={`pnl-value ${status.realized_pnl_today >= 0 ? "positive" : "negative"}`}>
            {status.realized_pnl_today >= 0 ? "+" : ""}
            {status.realized_pnl_today.toFixed(2)}
          </span>
          <span className="pnl-label">PnL Today</span>
        </div>
      </div>

      {/* Error Display */}
      {(actionError || status.last_error) && (
        <div className="execution-error">
          {actionError || status.last_error}
        </div>
      )}

      {/* Control Buttons */}
      <div className="execution-controls">
        {!status.connected ? (
          <button
            className="exec-btn connect-btn"
            onClick={handleConnect}
            disabled={isActioning || !igConfigured}
            title={!igConfigured ? "IG credentials not configured" : "Connect to IG"}
          >
            {isActioning ? "Connecting..." : "Connect"}
          </button>
        ) : (
          <button
            className="exec-btn disconnect-btn"
            onClick={handleDisconnect}
            disabled={isActioning}
          >
            {isActioning ? "..." : "Disconnect"}
          </button>
        )}

        {status.connected && !status.kill_switch_active && (
          <>
            {!status.armed ? (
              <button
                className="exec-btn arm-btn"
                onClick={handleArm}
                disabled={isActioning}
              >
                {isActioning ? "..." : "ARM"}
              </button>
            ) : (
              <button
                className="exec-btn disarm-btn"
                onClick={handleDisarm}
                disabled={isActioning}
              >
                {isActioning ? "..." : "DISARM"}
              </button>
            )}
          </>
        )}

        {status.connected && (
          <>
            {!status.kill_switch_active ? (
              <button
                className="exec-btn kill-btn"
                onClick={handleKillSwitch}
                disabled={isActioning}
                title="Emergency stop - disarms and blocks all trading"
              >
                KILL
              </button>
            ) : (
              <button
                className="exec-btn reset-kill-btn"
                onClick={handleResetKillSwitch}
                disabled={isActioning}
              >
                Reset Kill Switch
              </button>
            )}
          </>
        )}
      </div>

      {/* Kill Switch Warning */}
      {status.kill_switch_active && (
        <div className="kill-switch-warning">
          KILL SWITCH ACTIVE - Trading Halted
        </div>
      )}
    </div>
  );
}
