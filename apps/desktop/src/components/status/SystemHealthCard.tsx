import { memo } from "react";
import { SystemMetrics } from "../../hooks/useEngineHealth";
import { InfoTip } from "../InfoTip";

interface SystemHealthCardProps {
  metrics?: SystemMetrics;
  uptime: string;
}

export const SystemHealthCard = memo(function SystemHealthCard({
  metrics,
  uptime,
}: SystemHealthCardProps) {
  return (
    <div className="terminal-card">
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Infrastructure
          <InfoTip text="Engine resource utilization. Monitoring CPU and disk is critical for high-frequency operations and logging integrity." />
        </span>
      </div>
      <div className="terminal-card-body">
        <div className="dense-row">
          <span className="dense-label">CPU Usage</span>
          <span className={`dense-value num ${metrics && metrics.cpu_pct > 80 ? "text-red" : ""}`}>
            {metrics ? `${metrics.cpu_pct}%` : "\u2014"}
          </span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Memory</span>
          <span className="dense-value num">
            {metrics ? `${metrics.memory_usage_mb.toFixed(1)} MB` : "\u2014"}
          </span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Disk Free</span>
          <span className={`dense-value num ${metrics && metrics.disk_free_gb < 5 ? "text-red" : ""}`}>
            {metrics ? `${metrics.disk_free_gb.toFixed(1)} GB` : "\u2014"}
          </span>
        </div>
        <div className="dense-row" style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border-color)" }}>
          <span className="dense-label">Process ID</span>
          <span className="dense-value mono">{metrics?.process_id ?? "\u2014"}</span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Uptime</span>
          <span className="dense-value num">{uptime}</span>
        </div>
      </div>
    </div>
  );
});
