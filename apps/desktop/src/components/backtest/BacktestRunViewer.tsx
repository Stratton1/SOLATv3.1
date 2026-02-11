/**
 * Backtest run viewer - detailed view of a single backtest.
 *
 * Shows:
 * - Metrics summary
 * - Per-bot breakdown
 * - Trades table
 * - Equity curve
 */

import { useState, useEffect, useCallback } from "react";
import {
  engineClient,
  BacktestResultsResponse,
  BacktestTradesResponse,
  BacktestEquityResponse,
} from "../../lib/engineClient";

interface BacktestRunViewerProps {
  runId: string;
  onBack: () => void;
}

type Tab = "metrics" | "trades" | "equity";

export function BacktestRunViewer({ runId, onBack }: BacktestRunViewerProps) {
  const [activeTab, setActiveTab] = useState<Tab>("metrics");
  const [results, setResults] = useState<BacktestResultsResponse | null>(null);
  const [trades, setTrades] = useState<BacktestTradesResponse | null>(null);
  const [equity, setEquity] = useState<BacktestEquityResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch results on mount
  useEffect(() => {
    async function fetchResults() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await engineClient.getBacktestResults(runId);
        setResults(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch results");
      } finally {
        setIsLoading(false);
      }
    }
    fetchResults();
  }, [runId]);

  // Fetch trades when tab is selected
  const fetchTrades = useCallback(async () => {
    if (trades) return;
    try {
      const data = await engineClient.getBacktestTrades(runId, { limit: 100 });
      setTrades(data);
    } catch (err) {
      console.error("Failed to fetch trades:", err);
    }
  }, [runId, trades]);

  // Fetch equity when tab is selected
  const fetchEquity = useCallback(async () => {
    if (equity) return;
    try {
      const data = await engineClient.getBacktestEquity(runId, { limit: 1000 });
      setEquity(data);
    } catch (err) {
      console.error("Failed to fetch equity:", err);
    }
  }, [runId, equity]);

  useEffect(() => {
    if (activeTab === "trades") fetchTrades();
    if (activeTab === "equity") fetchEquity();
  }, [activeTab, fetchTrades, fetchEquity]);

  if (isLoading) {
    return (
      <div className="backtest-viewer">
        <div className="loading-container">
          <div className="loading-spinner" />
          <span className="loading-text">Loading results...</span>
        </div>
      </div>
    );
  }

  if (error || !results) {
    return (
      <div className="backtest-viewer">
        <div className="viewer-header">
          <button className="back-btn" onClick={onBack}>
            ← Back
          </button>
          <h2>Run: {runId}</h2>
        </div>
        <div className="error-container">
          <span className="error-title">Failed to load results</span>
          <span className="error-message">{error}</span>
        </div>
      </div>
    );
  }

  // Handle failed backtests (ok: false)
  if (!results.ok) {
    return (
      <div className="backtest-viewer">
        <div className="viewer-header">
          <button className="back-btn" onClick={onBack}>
            ← Back
          </button>
          <h2>Run: {runId}</h2>
        </div>
        <div className="error-container">
          <span className="error-title">Backtest Failed</span>
          {results.errors && results.errors.length > 0 ? (
            <div style={{ marginTop: "1rem" }}>
              {results.errors.map((err, idx) => (
                <div key={idx} className="error-message" style={{ marginBottom: "0.5rem" }}>
                  {err}
                </div>
              ))}
            </div>
          ) : (
            <span className="error-message">No error details available</span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="backtest-viewer">
      <div className="viewer-header">
        <button className="back-btn" onClick={onBack}>
          ← Back
        </button>
        <h2>Run: {runId}</h2>
        <span className={`status-badge ${results.ok ? "success" : "error"}`}>
          {results.ok ? "Success" : "Failed"}
        </span>
      </div>

      <div className="viewer-tabs">
        <button
          className={`viewer-tab ${activeTab === "metrics" ? "active" : ""}`}
          onClick={() => setActiveTab("metrics")}
        >
          Metrics
        </button>
        <button
          className={`viewer-tab ${activeTab === "trades" ? "active" : ""}`}
          onClick={() => setActiveTab("trades")}
        >
          Trades
        </button>
        <button
          className={`viewer-tab ${activeTab === "equity" ? "active" : ""}`}
          onClick={() => setActiveTab("equity")}
        >
          Equity Curve
        </button>
      </div>

      <div className="viewer-content">
        {activeTab === "metrics" && (
          <MetricsTab results={results} />
        )}
        {activeTab === "trades" && (
          <TradesTab trades={trades} />
        )}
        {activeTab === "equity" && (
          <EquityTab equity={equity} />
        )}
      </div>

      {results.warnings.length > 0 && (
        <div className="viewer-warnings">
          <h4>Warnings</h4>
          <ul>
            {results.warnings.slice(0, 10).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MetricsTab({ results }: { results: BacktestResultsResponse }) {
  const m = results.metrics;

  if (!m) {
    return <div className="metrics-empty">No metrics available</div>;
  }

  return (
    <div className="metrics-tab">
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-label">Total Return</span>
          <span className={`metric-value ${m.total_return >= 0 ? "positive" : "negative"}`}>
            {(m.total_return * 100).toFixed(2)}%
          </span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Sharpe Ratio</span>
          <span className="metric-value">{m.sharpe_ratio.toFixed(2)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Max Drawdown</span>
          <span className="metric-value negative">
            {(m.max_drawdown_pct * 100).toFixed(2)}%
          </span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Win Rate</span>
          <span className="metric-value">{(m.win_rate * 100).toFixed(1)}%</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Total Trades</span>
          <span className="metric-value">{m.total_trades}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Profit Factor</span>
          <span className="metric-value">{m.profit_factor.toFixed(2)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Avg Win</span>
          <span className="metric-value positive">{m.avg_win.toFixed(2)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Avg Loss</span>
          <span className="metric-value negative">{m.avg_loss.toFixed(2)}</span>
        </div>
      </div>

      {results.per_bot_summary.length > 0 && (
        <div className="per-bot-section">
          <h4>Per-Bot Breakdown</h4>
          <div className="per-bot-table">
            <div className="table-header">
              <span>Bot</span>
              <span>Symbols</span>
              <span>Trades</span>
              <span>Win Rate</span>
              <span>Sharpe</span>
              <span>PnL</span>
            </div>
            {results.per_bot_summary.map((bot, i) => (
              <div key={i} className="table-row">
                <span>{bot.bot}</span>
                <span>{bot.symbols_traded}</span>
                <span>{bot.trades_count}</span>
                <span>{(bot.win_rate * 100).toFixed(1)}%</span>
                <span>{bot.sharpe.toFixed(2)}</span>
                <span className={bot.pnl >= 0 ? "positive" : "negative"}>
                  {bot.pnl.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TradesTab({ trades }: { trades: BacktestTradesResponse | null }) {
  if (!trades) {
    return (
      <div className="loading-container">
        <div className="loading-spinner" />
        <span className="loading-text">Loading trades...</span>
      </div>
    );
  }

  if (trades.trades.length === 0) {
    return <div className="trades-empty">No trades recorded</div>;
  }

  return (
    <div className="trades-tab">
      <div className="trades-summary">
        Showing {trades.trades.length} of {trades.total} trades
      </div>
      <div className="trades-table">
        <div className="table-header">
          <span className="col-time">Entry</span>
          <span className="col-symbol">Symbol</span>
          <span className="col-dir">Dir</span>
          <span className="col-entry">Entry</span>
          <span className="col-exit">Exit</span>
          <span className="col-pnl">PnL</span>
          <span className="col-bot">Bot</span>
        </div>
        {trades.trades.map((trade, i) => (
          <div key={i} className="table-row">
            <span className="col-time">{formatDate((trade as { entry_time?: string }).entry_time)}</span>
            <span className="col-symbol">{trade.symbol ?? "-"}</span>
            <span className={`col-dir ${getDirectionClass(trade)}`}>
              {getDirectionLabel(trade)}
            </span>
            <span className="col-entry">{formatNumber(trade.entry_price, 5)}</span>
            <span className="col-exit">{formatNumber(trade.exit_price, 5)}</span>
            <span className={`col-pnl ${getPnlClass(trade.pnl)}`}>
              {formatNumber(trade.pnl, 2)}
            </span>
            <span className="col-bot">{trade.bot ?? "-"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function getDirectionLabel(trade: { direction?: string; side?: string }): string {
  return (trade.direction ?? trade.side ?? "UNKNOWN").toUpperCase();
}

function getDirectionClass(trade: { direction?: string; side?: string }): string {
  const normalized = getDirectionLabel(trade).toLowerCase();
  if (normalized === "buy" || normalized === "long") return "buy";
  if (normalized === "sell" || normalized === "short") return "sell";
  return "unknown";
}

function getPnlClass(pnl: unknown): string {
  return typeof pnl === "number" && pnl >= 0 ? "positive" : "negative";
}

function formatNumber(value: unknown, decimals: number): string {
  return typeof value === "number" ? value.toFixed(decimals) : "-";
}

function formatDate(value: unknown): string {
  if (typeof value !== "string") return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "-" : parsed.toLocaleDateString();
}

function EquityTab({ equity }: { equity: BacktestEquityResponse | null }) {
  if (!equity) {
    return (
      <div className="loading-container">
        <div className="loading-spinner" />
        <span className="loading-text">Loading equity curve...</span>
      </div>
    );
  }

  if (equity.points.length === 0) {
    return <div className="equity-empty">No equity data available</div>;
  }

  // Simple text-based representation for now
  const start = equity.points[0].equity;
  const end = equity.points[equity.points.length - 1].equity;
  const change = ((end - start) / start) * 100;
  const maxEquity = Math.max(...equity.points.map((p) => p.equity));
  const minEquity = Math.min(...equity.points.map((p) => p.equity));

  return (
    <div className="equity-tab">
      <div className="equity-summary">
        <div className="equity-stat">
          <span className="label">Start</span>
          <span className="value">{start.toFixed(2)}</span>
        </div>
        <div className="equity-stat">
          <span className="label">End</span>
          <span className="value">{end.toFixed(2)}</span>
        </div>
        <div className="equity-stat">
          <span className="label">Change</span>
          <span className={`value ${change >= 0 ? "positive" : "negative"}`}>
            {change.toFixed(2)}%
          </span>
        </div>
        <div className="equity-stat">
          <span className="label">High</span>
          <span className="value">{maxEquity.toFixed(2)}</span>
        </div>
        <div className="equity-stat">
          <span className="label">Low</span>
          <span className="value">{minEquity.toFixed(2)}</span>
        </div>
      </div>

      <div className="equity-chart-placeholder">
        <p>Equity curve visualization</p>
        <p className="hint">{equity.points.length} data points</p>
      </div>
    </div>
  );
}
