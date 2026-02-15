/**
 * Dashboard — Bloomberg-style dense grid with KPIs, control panel,
 * active strategies, positions, watchlist, equity curve, and signals.
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import Plotly from "plotly.js-finance-dist";
import { PlotlyChart } from "../components/PlotlyChart";
import { SummaryBar } from "../components/ui/SummaryBar";
import { useExecutionStatus } from "../hooks/useExecutionStatus";
import { useEngineHealth } from "../hooks/useEngineHealth";
import { useToast } from "../context/ToastContext";
import {
  engineClient,
  ExecutionFill,
  OpenPosition,
  Quote,
  AutopilotCombo,
  TerminalSignal,
} from "../lib/engineClient";
import { formatCurrency, formatPnl } from "../lib/format";

// =============================================================================
// Component
// =============================================================================

export function DashboardScreen() {
  const navigate = useNavigate();
  const { status, connect, arm } = useExecutionStatus();
  const { health, connectionState } = useEngineHealth();
  const { showToast } = useToast();

  // Data state
  const [fills, setFills] = useState<ExecutionFill[]>([]);
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [combos, setCombos] = useState<AutopilotCombo[]>([]);
  const [signals, setSignals] = useState<TerminalSignal[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);

  // Fetch fills for equity curve
  const fetchFills = useCallback(async () => {
    try {
      const res = await engineClient.getExecutionFills({ limit: 500 });
      setFills(res.fills);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch positions
  const fetchPositions = useCallback(async () => {
    try {
      const res = await engineClient.getPositions();
      setPositions(res.positions);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch quotes
  const fetchQuotes = useCallback(async () => {
    try {
      const res = await engineClient.getQuotes();
      setQuotes(res.quotes);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch autopilot combos
  const fetchCombos = useCallback(async () => {
    try {
      const res = await engineClient.getAutopilotCombos();
      setCombos(res.combos);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Fetch recent signals
  const fetchSignals = useCallback(async () => {
    try {
      const res = await engineClient.getTerminalSignals({ limit: 20 });
      setSignals(res.signals);
    } catch {
      /* engine may be offline */
    }
  }, []);

  // Set up polling
  useEffect(() => {
    fetchFills();
    fetchPositions();
    fetchQuotes();
    fetchCombos();
    fetchSignals();

    const intervals = [
      setInterval(fetchFills, 30000),
      setInterval(fetchPositions, 5000),
      setInterval(fetchQuotes, 3000),
      setInterval(fetchCombos, 10000),
      setInterval(fetchSignals, 5000),
    ];

    return () => intervals.forEach(clearInterval);
  }, [fetchFills, fetchPositions, fetchQuotes, fetchCombos, fetchSignals]);

  // Derived values
  const engineUp = connectionState === "connected";
  const balance = status?.account_balance;
  const pnlToday = status?.realized_pnl_today ?? 0;
  const openCount = status?.open_position_count ?? 0;
  const mode = status?.mode ?? "---";
  const brokerConnected = status?.connected ?? false;
  const isArmed = status?.armed ?? false;

  // Build equity data from fills
  const equityData = useMemo(() => {
    const startingBalance = status?.account_balance ?? 10000;
    let running = startingBalance;
    const sorted = [...fills].sort(
      (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime()
    );
    const points: { time: string; value: number }[] = [];
    for (const fill of sorted) {
      if (fill.pnl != null) running += fill.pnl;
      points.push({ time: fill.ts.slice(0, 10), value: running });
    }
    const byDate = new Map<string, number>();
    for (const p of points) byDate.set(p.time, p.value);
    return Array.from(byDate.entries()).map(([time, value]) => ({ time, value }));
  }, [fills, status?.account_balance]);

  // Equity trace
  const equityTraceData: Plotly.Data[] = useMemo(() => {
    if (equityData.length === 0) return [];
    return [
      {
        type: "scatter" as const,
        mode: "lines" as const,
        x: equityData.map((p) => p.time),
        y: equityData.map((p) => p.value),
        fill: "tozeroy" as const,
        fillcolor: "rgba(61, 139, 253, 0.12)",
        line: { color: "#3d8bfd", width: 2 },
        showlegend: false,
        hoverinfo: "x+y" as const,
      },
    ];
  }, [equityData]);

  // 3B: Control panel handlers
  const handleTestEngine = useCallback(async () => {
    try {
      const h = await engineClient.getHealth();
      showToast(`Engine: ${h.status} (v${h.version})`, "success");
    } catch {
      showToast("Engine unreachable", "error");
    }
  }, [showToast]);

  const handleConnectBroker = useCallback(async () => {
    try {
      const res = await connect();
      showToast(res.ok ? "Broker connected" : `Connection failed: ${res.error}`, res.ok ? "success" : "error");
    } catch {
      showToast("Connection failed", "error");
    }
  }, [connect, showToast]);

  const handleSyncHistory = useCallback(async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    try {
      showToast("Syncing 30 days of history...", "info");
      await engineClient.quickSync(30);
      showToast("History sync complete", "success");
    } catch {
      showToast("Sync failed", "error");
    } finally {
      setIsSyncing(false);
    }
  }, [isSyncing, showToast]);

  const handleStartDemo = useCallback(async () => {
    try {
      const res = await arm(true);
      showToast(res.armed ? "DEMO armed" : `Arm failed: ${res.error}`, res.armed ? "success" : "error");
    } catch {
      showToast("Arm failed", "error");
    }
  }, [arm, showToast]);

  return (
    <div className="screen-layout">
      <SummaryBar
        pageId="dashboard"
        title="Dashboard"
        description="Live overview of your trading activity. KPIs, positions, watchlist, equity curve, and recent signals at a glance."
        actions={[
          "Monitor open positions and daily P&L",
          "Use control panel to connect and arm",
          "Check active strategies and signal activity",
        ]}
        chips={[
          { label: "Mode", value: mode, variant: mode === "LIVE" ? "danger" : "info" },
          { label: "Positions", value: `${openCount}`, variant: openCount > 0 ? "warning" : "default" },
          { label: "Engine", value: engineUp ? "Online" : "Offline", variant: engineUp ? "success" : "danger" },
        ]}
      />
    <div className="dashboard-bloomberg">
      {/* Row 0: KPI Strip — 3A compact */}
      <div className="dash-kpi-strip">
        <div className="dash-kpi">
          <span className="dash-kpi-label">BALANCE</span>
          <span className="dash-kpi-value">
            {balance != null ? formatCurrency(balance) : (brokerConnected ? "Loading..." : "Not Connected")}
          </span>
        </div>
        <div className={`dash-kpi ${pnlToday >= 0 ? "kpi-pos" : "kpi-neg"}`}>
          <span className="dash-kpi-label">DAILY P&L</span>
          <span className="dash-kpi-value">
            {formatPnl(pnlToday)}
          </span>
        </div>
        <div className="dash-kpi">
          <span className="dash-kpi-label">POSITIONS</span>
          <span className="dash-kpi-value">{openCount}</span>
        </div>
        <div className="dash-kpi">
          <span className="dash-kpi-label">BOTS</span>
          <span className="dash-kpi-value">{combos.length || "0"}</span>
        </div>
        <div className="dash-kpi">
          <span className="dash-kpi-label">MODE</span>
          <span className={`dash-kpi-value mode-badge mode-${mode.toLowerCase()}`}>{mode}</span>
        </div>
        <div className="dash-kpi">
          <span className="dash-kpi-label">ENGINE</span>
          <span className="dash-kpi-value">
            <span className={`dash-led ${engineUp ? "led-ok" : "led-err"}`} />
            {engineUp ? `v${health?.version ?? "?"}` : "Offline"}
          </span>
        </div>
      </div>

      {/* Row 1: Control Panel + Active Strategies */}
      <div className="dash-widget dash-area-control">
        <div className="dash-widget-header">
          <span>CONTROL</span>
        </div>
        <div className="dash-widget-body dash-control-grid">
          <button className="dash-ctrl-btn" onClick={handleTestEngine}>
            <span className="ctrl-icon">{"\u2699"}</span>
            <span className="ctrl-label">Test Engine</span>
            <span className={`ctrl-state ${engineUp ? "state-ok" : "state-err"}`}>
              {engineUp ? "Online" : "Offline"}
            </span>
          </button>
          <button className="dash-ctrl-btn" onClick={handleConnectBroker}>
            <span className="ctrl-icon">{"\u2197"}</span>
            <span className="ctrl-label">Connect Broker</span>
            <span className={`ctrl-state ${brokerConnected ? "state-ok" : "state-err"}`}>
              {brokerConnected ? "Connected" : "Disconnected"}
            </span>
          </button>
          <button className="dash-ctrl-btn" onClick={handleSyncHistory} disabled={isSyncing}>
            <span className="ctrl-icon">{isSyncing ? "\u23F3" : "\u21BB"}</span>
            <span className="ctrl-label">Sync History</span>
            <span className="ctrl-state">{isSyncing ? "Syncing..." : "Ready"}</span>
          </button>
          <button className="dash-ctrl-btn" onClick={handleStartDemo}>
            <span className="ctrl-icon">{"\u25B6"}</span>
            <span className="ctrl-label">Start DEMO</span>
            <span className={`ctrl-state ${isArmed ? "state-ok" : "state-err"}`}>
              {isArmed ? "Armed" : "Standby"}
            </span>
          </button>
        </div>
      </div>

      <div className="dash-widget dash-area-strategies">
        <div className="dash-widget-header">
          <span>ACTIVE STRATEGIES</span>
          <span className="dash-widget-count">{combos.length}</span>
        </div>
        <div className="dash-widget-body scroll-area">
          {combos.length > 0 ? (
            <table className="dash-widget-table">
              <thead>
                <tr>
                  <th>Bot</th>
                  <th>Symbol</th>
                  <th>TF</th>
                  <th>Buffer</th>
                </tr>
              </thead>
              <tbody>
                {combos.map((c, i) => (
                  <tr
                    key={i}
                    className="dash-row-clickable"
                    onClick={() => navigate("/terminal")}
                  >
                    <td className="mono">{c.bot}</td>
                    <td>{c.symbol}</td>
                    <td>{c.timeframe}</td>
                    <td className="num">{c.buffer_size}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dash-widget-empty">
              No active strategies
              <span className="dash-widget-hint">Enable Autopilot in System</span>
            </div>
          )}
        </div>
      </div>

      {/* Row 2: Positions + Watchlist */}
      <div className="dash-widget dash-area-positions">
        <div className="dash-widget-header">
          <span>OPEN POSITIONS</span>
          <span className="dash-widget-count">{positions.length}</span>
        </div>
        <div className="dash-widget-body scroll-area">
          {positions.length > 0 ? (
            <table className="dash-widget-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Dir</th>
                  <th>Size</th>
                  <th>Entry</th>
                  <th>PnL</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={i}>
                    <td className="mono">{p.symbol}</td>
                    <td>
                      <span className={`dir-badge dir-${p.direction.toLowerCase()}`}>
                        {p.direction}
                      </span>
                    </td>
                    <td className="num">{p.size}</td>
                    <td className="num">{p.entry_price != null ? p.entry_price.toFixed(5) : "---"}</td>
                    <td className={`num ${(p.pnl ?? 0) >= 0 ? "positive" : "negative"}`}>
                      {p.pnl != null ? p.pnl.toFixed(2) : "---"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dash-widget-empty">No open positions</div>
          )}
        </div>
      </div>

      <div className="dash-widget dash-area-watchlist">
        <div className="dash-widget-header">
          <span>WATCHLIST</span>
          <span className="dash-widget-count">{Object.keys(quotes).length}</span>
        </div>
        <div className="dash-widget-body scroll-area">
          {Object.keys(quotes).length > 0 ? (
            <table className="dash-widget-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Bid</th>
                  <th>Ask</th>
                  <th>Spread</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(quotes).map((q, i) => (
                  <tr key={i}>
                    <td className="mono">{q.symbol}</td>
                    <td className="num">{q.bid != null ? q.bid.toFixed(5) : "---"}</td>
                    <td className="num">{q.ask != null ? q.ask.toFixed(5) : "---"}</td>
                    <td className="num">
                      {q.bid != null && q.ask != null
                        ? ((q.ask - q.bid) * 10000).toFixed(1)
                        : "---"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dash-widget-empty">
              Connect broker for live quotes
            </div>
          )}
        </div>
      </div>

      {/* Row 3: Equity Curve + Recent Signals */}
      <div className="dash-widget dash-area-equity">
        <div className="dash-widget-header">
          <span>EQUITY CURVE</span>
          <span className="dash-widget-count">{fills.length} fills</span>
        </div>
        <div className="dash-widget-body">
          <PlotlyChart
            data={equityTraceData}
            layout={{
              height: 160,
              margin: { l: 50, r: 10, t: 5, b: 25 },
              xaxis: { type: "date" as const, gridcolor: "#e8ebf0", linecolor: "#d5d9e0" },
              yaxis: { gridcolor: "#e8ebf0", linecolor: "#d5d9e0" },
              ...(equityData.length === 0 ? {
                annotations: [{
                  text: "No fill data yet",
                  xref: "paper" as const,
                  yref: "paper" as const,
                  x: 0.5,
                  y: 0.5,
                  showarrow: false,
                  font: { size: 12, color: "#9da5b4" },
                }],
              } : {}),
            }}
            config={{ displayModeBar: false, scrollZoom: false }}
          />
        </div>
      </div>

      <div className="dash-widget dash-area-signals">
        <div className="dash-widget-header">
          <span>RECENT SIGNALS</span>
          <span className="dash-widget-count">{signals.length}</span>
        </div>
        <div className="dash-widget-body scroll-area">
          {signals.length > 0 ? (
            <table className="dash-widget-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Bot</th>
                  <th>Symbol</th>
                  <th>Side</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s, i) => (
                  <tr key={i}>
                    <td className="num">
                      {s.ts ? new Date(s.ts).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "---"}
                    </td>
                    <td className="mono">{s.bot ?? "---"}</td>
                    <td>{s.symbol ?? "---"}</td>
                    <td>
                      {s.side ? (
                        <span className={`dir-badge dir-${s.side.toLowerCase()}`}>
                          {s.side}
                        </span>
                      ) : (
                        "---"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dash-widget-empty">No signals yet</div>
          )}
        </div>
      </div>
    </div>
    </div>
  );
}
