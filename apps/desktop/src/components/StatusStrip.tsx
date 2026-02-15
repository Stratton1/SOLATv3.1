/**
 * Bottom status strip — persistent 24px bar with mode badge,
 * connection indicator, latency, sync progress, and hotkey hints.
 */

import { useEffect, useState } from "react";
import { clampProgress } from "../lib/progress";

interface StatusStripProps {
  mode: string | null;
  engineVersion: string | null;
  isConnected: boolean;
  currentPath: string;
}

const SCREEN_HOTKEYS: Record<string, Array<{ key: string; label: string }>> = {
  "/": [
    { key: "\u2318K", label: "Palette" },
    { key: "\u23182", label: "Terminal" },
  ],
  "/terminal": [
    { key: "\u2318K", label: "Palette" },
    { key: "\u2191\u2193", label: "Zoom" },
  ],
  "/backtests": [
    { key: "\u2318K", label: "Palette" },
    { key: "R", label: "Run" },
  ],
  "/optimise": [
    { key: "\u2318K", label: "Palette" },
  ],
  "/blotter": [
    { key: "\u2318K", label: "Palette" },
    { key: "\u2318C", label: "Copy" },
  ],
};

export function StatusStrip({
  mode,
  engineVersion,
  isConnected,
  currentPath,
}: StatusStripProps) {
  const modeClass = mode === "LIVE" ? "live" : "demo";
  const hints = SCREEN_HOTKEYS[currentPath] ?? SCREEN_HOTKEYS["/"];
  
  // Fake latency for prototype feel (would be real in production)
  const [latency, setLatency] = useState(12);
  // Fake sync state for demonstration
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setLatency(10 + Math.floor(Math.random() * 15));
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="status-strip">
      <div className="status-strip-left">
        <span className={`strip-mode-badge ${modeClass}`}>
          {mode ?? "DEMO"}
        </span>
        
        <div className="status-item connection-item">
          <span className={`strip-connection-dot ${isConnected ? "pulse" : "disconnected"}`} />
          <span className="status-text">{isConnected ? "Connected" : "Offline"}</span>
          {isConnected && <span className="latency-text">{latency}ms</span>}
        </div>

        {engineVersion && <div className="status-item">v{engineVersion}</div>}
        
        {isSyncing && (
           <div className="status-item sync-item">
             <span className="sync-icon spinning">↻</span>
             <span className="sync-label">Syncing...</span>
             <div className="sync-progress-track">
               <div className="sync-progress-fill" style={{ width: `${clampProgress(syncProgress)}%` }} />
             </div>
           </div>
        )}
      </div>

      <div className="status-strip-right">
        {hints.map((h) => (
          <span key={h.key} className="strip-hotkey">
            <kbd>{h.key}</kbd> {h.label}
          </span>
        ))}
      </div>
    </div>
  );
}
