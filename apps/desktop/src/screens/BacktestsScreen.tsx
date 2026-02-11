/**
 * Backtests screen - list, view, and compare backtest runs.
 *
 * Features:
 * - List all backtest runs with status
 * - Click to view detailed results
 * - Multi-select runs for comparison
 * - Comparison metrics table
 */

import { useState, useMemo, useCallback } from "react";
import { useBacktestRuns } from "../hooks/useBacktestRuns";
import { BacktestRunSummary } from "../lib/engineClient";
import { BacktestRunViewer } from "../components/backtest/BacktestRunViewer";
import { BacktestComparison } from "../components/backtest/BacktestComparison";
import { BacktestWizard } from "../components/backtest/BacktestWizard";
import { InfoTip } from "../components/InfoTip";

export function BacktestsScreen() {
  const { runs, isLoading, error, refetch } = useBacktestRuns();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [compareRunIds, setCompareRunIds] = useState<Set<string>>(new Set());
  const [showComparison, setShowComparison] = useState(false);
  const [showWizard, setShowWizard] = useState(false);

  const toggleCompare = useCallback(
    (runId: string) => {
      setCompareRunIds((prev) => {
        const next = new Set(prev);
        if (next.has(runId)) {
          next.delete(runId);
        } else if (next.size < 5) {
          next.add(runId);
        }
        return next;
      });
    },
    []
  );

  const clearComparison = useCallback(() => {
    setCompareRunIds(new Set());
    setShowComparison(false);
  }, []);

  const compareRuns = useMemo(
    () => runs.filter((r) => compareRunIds.has(r.run_id)),
    [runs, compareRunIds]
  );

  if (isLoading) {
    return (
      <div className="backtests-screen">
        <div style={{ padding: "20px" }}>
          <div className="skeleton skeleton-row" style={{ width: "40%", height: 24, marginBottom: 16 }} />
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="backtests-screen">
        <div className="error-container">
          <span className="error-icon">!</span>
          <span className="error-title">Failed to load backtests</span>
          <span className="error-message">{error}</span>
          <button className="retry-btn" onClick={refetch}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (selectedRunId) {
    return (
      <BacktestRunViewer
        runId={selectedRunId}
        onBack={() => setSelectedRunId(null)}
      />
    );
  }

  if (showComparison && compareRuns.length >= 2) {
    return (
      <BacktestComparison
        runs={compareRuns}
        onBack={() => setShowComparison(false)}
        onClear={clearComparison}
      />
    );
  }

  return (
    <div className="backtests-screen">
      <div className="backtests-header">
        <h2>
          Backtest Runs
          <InfoTip text="Backtests replay historical bar data through your strategies to evaluate performance. Each run shows Sharpe ratio, trade count, and total return. Select multiple runs (up to 5) to compare side-by-side." />
        </h2>
        <div className="backtests-header-actions">
          <button
            className="wizard-btn primary"
            style={{ padding: "6px 14px", fontSize: 13 }}
            onClick={() => setShowWizard(true)}
          >
            New Backtest
          </button>
          {compareRunIds.size >= 2 && (
            <button
              className="compare-btn"
              onClick={() => setShowComparison(true)}
            >
              Compare ({compareRunIds.size})
            </button>
          )}
          {compareRunIds.size > 0 && (
            <button className="clear-compare-btn" onClick={clearComparison}>
              Clear
            </button>
          )}
          <button className="refresh-btn" onClick={refetch}>
            Refresh
          </button>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="backtests-empty">
          <p className="backtests-empty-title">No backtest runs yet</p>
          <p className="backtests-empty-hint">
            Run your first backtest to evaluate strategy performance on
            historical data. Click "New Backtest" above, or open the Terminal
            and use the Strategy drawer.
          </p>
          <p className="backtests-empty-hint">
            You can also run backtests from the command line using the grand
            sweep script for bulk testing across all symbols and timeframes.
          </p>
          <button
            className="wizard-btn primary"
            style={{ marginTop: 12 }}
            onClick={() => setShowWizard(true)}
          >
            Run Your First Backtest
          </button>
        </div>
      ) : (
        <div className="backtests-list">
          <div className="backtests-table">
            <div className="table-header">
              <span className="col-check"></span>
              <span className="col-id">Run ID</span>
              <span className="col-status">Status</span>
              <span className="col-bots">Bots</span>
              <span className="col-symbols">Symbols</span>
              <span className="col-timeframe">TF</span>
              <span className="col-trades">Trades</span>
              <span className="col-sharpe">Sharpe</span>
              <span className="col-return">Return</span>
            </div>
            {runs.map((run) => (
              <BacktestRunRow
                key={run.run_id}
                run={run}
                isSelected={compareRunIds.has(run.run_id)}
                onToggleCompare={() => toggleCompare(run.run_id)}
                onClick={() => setSelectedRunId(run.run_id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Backtest Wizard */}
      {showWizard && (
        <BacktestWizard
          onClose={() => setShowWizard(false)}
          onComplete={(runId) => {
            setShowWizard(false);
            refetch();
            setSelectedRunId(runId);
          }}
        />
      )}
    </div>
  );
}

interface BacktestRunRowProps {
  run: BacktestRunSummary;
  isSelected: boolean;
  onToggleCompare: () => void;
  onClick: () => void;
}

function BacktestRunRow({ run, isSelected, onToggleCompare, onClick }: BacktestRunRowProps) {
  const statusClass = run.status === "done" ? "success" : run.status === "failed" ? "error" : "pending";

  return (
    <div className={`table-row ${isSelected ? "row-selected" : ""}`}>
      <span className="col-check">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggleCompare}
          className="compare-checkbox"
        />
      </span>
      <button className="table-row-content" onClick={onClick}>
        <span className="col-id">{run.run_id}</span>
        <span className={`col-status ${statusClass}`}>
          {run.status}
        </span>
        <span className="col-bots">{run.bots.length > 0 ? run.bots.join(", ") : "—"}</span>
        <span className="col-symbols">
          {run.symbols.length > 0 ? run.symbols.slice(0, 2).join(", ") : "—"}
          {run.symbols.length > 2 && ` +${run.symbols.length - 2}`}
        </span>
        <span className="col-timeframe">{run.timeframe || "—"}</span>
        <span className="col-trades">{run.trades_count}</span>
        <span className="col-sharpe">
          {run.sharpe !== null && run.sharpe !== undefined
            ? run.sharpe.toFixed(2)
            : "—"}
        </span>
        <span className={`col-return ${(run.total_return ?? 0) >= 0 ? "positive" : "negative"}`}>
          {run.total_return !== null && run.total_return !== undefined
            ? `${(run.total_return * 100).toFixed(2)}%`
            : "—"}
        </span>
      </button>
    </div>
  );
}
