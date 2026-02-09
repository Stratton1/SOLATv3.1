/**
 * BacktestComparison - side-by-side comparison of multiple backtest runs.
 *
 * Shows:
 * - Metrics table (rows = metrics, columns = runs)
 * - Per-bot summary
 * - Top winners/losers highlight
 */

import { useState, useEffect, useMemo } from "react";
import {
  BacktestRunSummary,
  BacktestResultsResponse,
  BacktestMetrics,
  engineClient,
} from "../../lib/engineClient";

// =============================================================================
// Types
// =============================================================================

interface BacktestComparisonProps {
  runs: BacktestRunSummary[];
  onBack: () => void;
  onClear: () => void;
}

interface RunResults {
  runId: string;
  results: BacktestResultsResponse | null;
  loading: boolean;
  error: string | null;
}

// Colors for differentiating runs in comparison
const RUN_COLORS = ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#dc2626"];

// Metrics to display in comparison table
const COMPARISON_METRICS: Array<{
  key: keyof BacktestMetrics;
  label: string;
  format: (v: number) => string;
  higherIsBetter: boolean;
}> = [
  { key: "sharpe_ratio", label: "Sharpe Ratio", format: (v) => v.toFixed(2), higherIsBetter: true },
  { key: "sortino_ratio", label: "Sortino Ratio", format: (v) => v.toFixed(2), higherIsBetter: true },
  { key: "total_return", label: "Total Return", format: (v) => `${(v * 100).toFixed(2)}%`, higherIsBetter: true },
  { key: "annualized_return", label: "Annualized Return", format: (v) => `${(v * 100).toFixed(2)}%`, higherIsBetter: true },
  { key: "max_drawdown_pct", label: "Max Drawdown", format: (v) => `${v.toFixed(2)}%`, higherIsBetter: false },
  { key: "win_rate", label: "Win Rate", format: (v) => `${(v * 100).toFixed(1)}%`, higherIsBetter: true },
  { key: "profit_factor", label: "Profit Factor", format: (v) => v.toFixed(2), higherIsBetter: true },
  { key: "total_trades", label: "Total Trades", format: (v) => v.toFixed(0), higherIsBetter: false },
  { key: "winning_trades", label: "Winning Trades", format: (v) => v.toFixed(0), higherIsBetter: true },
  { key: "losing_trades", label: "Losing Trades", format: (v) => v.toFixed(0), higherIsBetter: false },
  { key: "avg_win", label: "Avg Win", format: (v) => v.toFixed(4), higherIsBetter: true },
  { key: "avg_loss", label: "Avg Loss", format: (v) => v.toFixed(4), higherIsBetter: false },
];

// =============================================================================
// Component
// =============================================================================

export function BacktestComparison({ runs, onBack, onClear }: BacktestComparisonProps) {
  const [runResults, setRunResults] = useState<RunResults[]>([]);

  // Fetch results for all runs
  useEffect(() => {
    const initial: RunResults[] = runs.map((r) => ({
      runId: r.run_id,
      results: null,
      loading: true,
      error: null,
    }));
    setRunResults(initial);

    runs.forEach((run, idx) => {
      engineClient
        .getBacktestResults(run.run_id)
        .then((results) => {
          setRunResults((prev) =>
            prev.map((r, i) =>
              i === idx ? { ...r, results, loading: false } : r
            )
          );
        })
        .catch((err) => {
          setRunResults((prev) =>
            prev.map((r, i) =>
              i === idx
                ? { ...r, loading: false, error: err.message ?? "Failed" }
                : r
            )
          );
        });
    });
  }, [runs]);

  const allLoaded = runResults.every((r) => !r.loading);
  const anyLoading = runResults.some((r) => r.loading);

  // Find best value for each metric (for highlighting)
  const bestValues = useMemo(() => {
    const best: Record<string, number> = {};
    COMPARISON_METRICS.forEach((metric) => {
      const values = runResults
        .filter((r) => r.results?.metrics)
        .map((r) => r.results!.metrics![metric.key] as number);

      if (values.length > 0) {
        best[metric.key] = metric.higherIsBetter
          ? Math.max(...values)
          : Math.min(...values);
      }
    });
    return best;
  }, [runResults]);

  return (
    <div className="backtests-screen">
      <div className="backtests-header">
        <div className="backtests-header-left">
          <button className="back-btn" onClick={onBack}>
            ← Back
          </button>
          <h2>Compare ({runs.length} runs)</h2>
        </div>
        <button className="clear-compare-btn" onClick={onClear}>
          Clear Selection
        </button>
      </div>

      {anyLoading && (
        <div className="comparison-loading">Loading results...</div>
      )}

      {allLoaded && (
        <div className="comparison-content">
          {/* Metrics Table */}
          <div className="comparison-table-wrapper">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th className="metric-label-col">Metric</th>
                  {runs.map((run, idx) => (
                    <th key={run.run_id} style={{ borderTopColor: RUN_COLORS[idx] }}>
                      <span
                        className="comparison-run-dot"
                        style={{ background: RUN_COLORS[idx] }}
                      />
                      <span className="comparison-run-id">
                        {run.run_id.slice(0, 12)}
                      </span>
                      <span className="comparison-run-bots">
                        {run.bots.join(", ")}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARISON_METRICS.map((metric) => (
                  <tr key={metric.key}>
                    <td className="metric-label">{metric.label}</td>
                    {runResults.map((rr) => {
                      const value = rr.results?.metrics?.[metric.key] as
                        | number
                        | undefined;
                      const isBest =
                        value !== undefined &&
                        bestValues[metric.key] === value &&
                        runResults.filter(
                          (r) => r.results?.metrics?.[metric.key] === value
                        ).length === 1;

                      return (
                        <td
                          key={rr.runId}
                          className={`metric-value ${isBest ? "metric-best" : ""}`}
                        >
                          {rr.error
                            ? "Error"
                            : value !== undefined
                              ? metric.format(value)
                              : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Per-bot Summary */}
          <div className="comparison-per-bot">
            <h3>Per-Bot Summary</h3>
            {runResults.map((rr, idx) => {
              if (!rr.results?.per_bot_summary?.length) return null;
              return (
                <div key={rr.runId} className="comparison-bot-section">
                  <div className="comparison-bot-header">
                    <span
                      className="comparison-run-dot"
                      style={{ background: RUN_COLORS[idx] }}
                    />
                    <span>{rr.runId.slice(0, 12)}</span>
                  </div>
                  <div className="comparison-bot-grid">
                    {rr.results.per_bot_summary.map((bot) => (
                      <div key={bot.bot} className="comparison-bot-card">
                        <span className="bot-card-name">{bot.bot}</span>
                        <div className="bot-card-stats">
                          <span>Sharpe: {bot.sharpe.toFixed(2)}</span>
                          <span>WR: {(bot.win_rate * 100).toFixed(0)}%</span>
                          <span>Trades: {bot.trades_count}</span>
                          <span
                            className={bot.pnl >= 0 ? "positive" : "negative"}
                          >
                            PnL: {bot.pnl.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
