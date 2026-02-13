import { memo } from "react";
import { GateStatusResponse } from "../../hooks/useRiskGates";
import { InfoTip } from "../InfoTip";

interface RiskGateMonitorProps {
  gates: GateStatusResponse | null;
  isLoading: boolean;
}

export const RiskGateMonitor = memo(function RiskGateMonitor({
  gates,
  isLoading,
}: RiskGateMonitorProps) {
  if (isLoading && !gates) {
    return <div className="terminal-card skeleton" style={{ height: 200 }} />;
  }

  return (
    <div className="terminal-card">
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Safety Gates
          <InfoTip text="Live execution safeguards. All gates must be GREEN to arm the engine in LIVE mode. Blockers indicate missing config or account mismatches." />
        </span>
        <span className={`card-badge ${gates?.allowed ? "live" : "demo"}`}>
          {gates?.allowed ? "PASSED" : "BLOCKED"}
        </span>
      </div>
      <div className="terminal-card-body">
        <div className="gate-grid">
          {gates?.blockers.map((blocker, i) => (
            <div key={i} className="gate-item blocked">
              <span className="gate-icon">{"\u2716"}</span>
              <span className="gate-text">{blocker}</span>
            </div>
          ))}
          {gates?.warnings.map((warning, i) => (
            <div key={i} className="gate-item warning">
              <span className="gate-icon">{"\u26A0"}</span>
              <span className="gate-text">{warning}</span>
            </div>
          ))}
          {gates && gates.blockers.length === 0 && (
            <div className="gate-item passed">
              <span className="gate-icon">{"\u2714"}</span>
              <span className="gate-text">All mandatory safety gates passed</span>
            </div>
          )}
        </div>
        <div className="gate-meta" style={{ marginTop: 12, fontSize: 10, color: "var(--text-muted)" }}>
          Mode: {gates?.mode} | {gates?.details?.live_trading_enabled ? "LIVE ENABLED" : "LIVE DISABLED"}
        </div>
      </div>
    </div>
  );
});
