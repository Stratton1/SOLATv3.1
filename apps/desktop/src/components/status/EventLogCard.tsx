import { memo } from "react";
import { useEngineLogs } from "../../hooks/useEngineLogs";
import { InfoTip } from "../InfoTip";

export const EventLogCard = memo(function EventLogCard() {
  const { logs, isLoading, error } = useEngineLogs("INFO", 50);

  const getLevelClass = (level: string) => {
    switch (level) {
      case "ERROR": return "text-red";
      case "WARNING": return "text-yellow";
      case "INFO": return "text-blue";
      default: return "";
    }
  };

  return (
    <div className="terminal-card" style={{ flex: 1, minHeight: "300px", overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          System Event Log
          <InfoTip text="Real-time stream of engine logs. High-priority errors and warnings are highlighted here for immediate visibility." />
        </span>
      </div>
      <div className="terminal-card-body" style={{ padding: 0, flex: 1, overflow: "hidden" }}>
        {isLoading && logs.length === 0 ? (
          <div className="skeleton" style={{ height: "100%" }} />
        ) : error ? (
          <div style={{ padding: 20, color: "var(--accent-red)" }}>{error}</div>
        ) : (
          <div className="scroll-area">
            <table className="terminal-signals-table dense mono" style={{ fontSize: 10 }}>
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Time</th>
                  <th style={{ width: 60 }}>Level</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log, i) => (
                  <tr key={i}>
                    <td className="num tabular-nums">
                      {new Date(log.timestamp).toLocaleTimeString([], { hour12: false })}
                    </td>
                    <td className={getLevelClass(log.level)} style={{ fontWeight: 600 }}>
                      {log.level}
                    </td>
                    <td style={{ color: "var(--text-secondary)", whiteSpace: "normal" }}>
                      {log.message}
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={3} style={{ textAlign: "center", padding: 20, color: "var(--text-muted)" }}>
                      NO LOGS RECORDED
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
});
