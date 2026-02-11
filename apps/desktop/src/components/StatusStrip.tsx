/**
 * Bottom status strip — persistent 24px bar with mode badge,
 * connection indicator, and hotkey hints.
 */

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
    { key: "Esc", label: "Close" },
  ],
  "/backtests": [
    { key: "\u2318K", label: "Palette" },
    { key: "\u23182", label: "Terminal" },
  ],
  "/optimise": [
    { key: "\u2318K", label: "Palette" },
    { key: "\u23182", label: "Terminal" },
  ],
  "/blotter": [
    { key: "\u2318K", label: "Palette" },
    { key: "\u23182", label: "Terminal" },
  ],
  "/settings": [
    { key: "\u2318K", label: "Palette" },
    { key: "\u23181", label: "Status" },
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

  return (
    <div className="status-strip">
      <div className="status-strip-left">
        <span className={`strip-mode-badge ${modeClass}`}>
          {mode ?? "DEMO"}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span className={`strip-connection-dot ${isConnected ? "" : "disconnected"}`} />
          {isConnected ? "Connected" : "Offline"}
        </span>
        {engineVersion && <span>v{engineVersion}</span>}
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
