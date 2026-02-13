import { memo } from "react";
import { HealthData, ConfigData } from "../../hooks/useEngineHealth";

interface MissionControlHeaderProps {
  health: HealthData | null;
  config: ConfigData | null;
  wsConnected: boolean;
  brokerAuthenticated?: boolean;
}

export const MissionControlHeader = memo(function MissionControlHeader({
  health,
  config,
  wsConnected,
  brokerAuthenticated,
}: MissionControlHeaderProps) {
  return (
    <header className="status-dashboard-header">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h2 style={{ fontSize: 14, fontWeight: 900, color: "var(--text-primary)", letterSpacing: "0.15em" }}>MISSION CONTROL</h2>
        <span className={`card-badge ${config?.mode === "LIVE" ? "live" : "demo"}`} style={{ fontSize: 10, padding: "2px 8px" }}>
          {config?.mode ?? "DEMO"}
        </span>
      </div>

      <div className="led-group">
        <div className="led-item">
          <div className={`led ${health?.status === "healthy" ? "active" : "error"}`} />
          REST
        </div>
        <div className="led-item">
          <div className={`led ${wsConnected ? "active" : "error"}`} />
          WS
        </div>
        <div className="led-item">
          <div className={`led ${brokerAuthenticated ? "active" : "error"}`} />
          IG
        </div>
        <div className="led-item" style={{ marginLeft: 12, borderLeft: "1px solid var(--border-color)", paddingLeft: 12 }}>
          <span className="dense-label" style={{ fontSize: 9 }}>v{health?.version ?? "\u2014"}</span>
        </div>
      </div>
    </header>
  );
});
