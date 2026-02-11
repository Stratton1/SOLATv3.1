/**
 * Optimisation Screen — scheduler status, proposals, recommendations, and combo selection.
 * UK spelling throughout (optimise, optimisation).
 */

import { useState, useCallback, useMemo, useEffect } from "react";
import { useOptimization } from "../hooks/useOptimization";
import { useRecommendations } from "../hooks/useRecommendations";
import { InfoTip } from "../components/InfoTip";
import { useToast } from "../context/ToastContext";
import { Proposal, engineClient, WalkForwardRequest, RecommendedSet, AllowlistGroup } from "../lib/engineClient";

function ProposalRow({
  proposal,
  onApply,
}: {
  proposal: Proposal;
  onApply: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isPending = proposal.status === "pending";
  const combosCount = proposal.selected_combos?.length ?? 0;

  return (
    <div className="opt-proposal-row">
      <div
        className="opt-proposal-header"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="opt-proposal-id">{proposal.proposal_id}</span>
        <span className={`opt-proposal-status opt-status-${proposal.status}`}>
          {proposal.status}
        </span>
        <span className="opt-proposal-combos">{combosCount} combos</span>
        <span className="opt-proposal-date">
          {new Date(proposal.created_at).toLocaleDateString()}
        </span>
        {isPending && (
          <button
            className="opt-apply-btn"
            onClick={(e) => {
              e.stopPropagation();
              onApply(proposal.proposal_id);
            }}
          >
            Apply (DEMO)
          </button>
        )}
        <span className="opt-expand-icon">{expanded ? "\u25B2" : "\u25BC"}</span>
      </div>

      {expanded && (
        <div className="opt-proposal-detail">
          {proposal.wfo_run_id && (
            <p className="opt-detail-meta">WFO Run: {proposal.wfo_run_id}</p>
          )}
          {proposal.message && (
            <p className="opt-detail-meta">{proposal.message}</p>
          )}

          {combosCount > 0 && (
            <table className="opt-combos-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Bot</th>
                  <th>TF</th>
                  <th>Sharpe</th>
                  <th>Trades</th>
                </tr>
              </thead>
              <tbody>
                {proposal.selected_combos.map((combo, i) => (
                  <tr key={i}>
                    <td>{(combo as Record<string, unknown>).symbol as string}</td>
                    <td>{(combo as Record<string, unknown>).bot as string}</td>
                    <td>{(combo as Record<string, unknown>).timeframe as string}</td>
                    <td>
                      {typeof (combo as Record<string, unknown>).avg_sharpe ===
                      "number"
                        ? ((combo as Record<string, unknown>).avg_sharpe as number).toFixed(2)
                        : "\u2014"}
                    </td>
                    <td>
                      {(combo as Record<string, unknown>).total_trades as number ?? "\u2014"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function WfoTriggerModal({ onClose, onComplete }: { onClose: () => void; onComplete: () => void }) {
  const { showToast } = useToast();
  const [symbols, setSymbols] = useState("EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD");
  const [minTrades, setMinTrades] = useState(10);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleRun = useCallback(async () => {
    setIsSubmitting(true);
    try {
      const now = new Date();
      const oneYearAgo = new Date(now);
      oneYearAgo.setFullYear(now.getFullYear() - 1);

      const request: WalkForwardRequest = {
        symbols: symbols.split(",").map((s) => s.trim()).filter(Boolean),
        bots: [],
        start_date: oneYearAgo.toISOString().split("T")[0],
        end_date: now.toISOString().split("T")[0],
        min_trades: minTrades,
      };
      const resp = await engineClient.startWalkForward(request);
      showToast(`Walk-forward started: ${resp.run_id}`, "success");
      onComplete();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to start walk-forward",
        "error"
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [symbols, minTrades, showToast, onComplete]);

  return (
    <div className="wfo-modal-backdrop" onClick={onClose}>
      <div className="wfo-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Run Walk-Forward Optimisation</h3>
        <div className="wizard-field">
          <label>Symbols (comma-separated)</label>
          <input
            type="text"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
          />
        </div>
        <div className="wizard-field">
          <label>Minimum Trades per Window</label>
          <input
            type="number"
            value={minTrades}
            onChange={(e) => setMinTrades(parseInt(e.target.value) || 5)}
            min={1}
            max={100}
          />
        </div>
        <div className="wfo-modal-actions">
          <button className="wizard-btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="wizard-btn primary"
            onClick={handleRun}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Starting..." : "Run WFO"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Group combos by symbol, then by timeframe within each symbol. */
function GroupedComboList({
  recSet,
  onApply,
}: {
  recSet: RecommendedSet;
  onApply: (id: string) => void;
}) {
  const grouped = useMemo(() => {
    const map = new Map<string, typeof recSet.combos>();
    for (const combo of recSet.combos) {
      const key = combo.symbol;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(combo);
    }
    return map;
  }, [recSet.combos]);

  return (
    <div className="recset-combos">
      {Array.from(grouped.entries()).map(([symbol, combos]) => (
        <div key={symbol} className="recset-symbol-group">
          <div className="combo-group-header">{symbol}</div>
          <table className="opt-combos-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Bot</th>
                <th>TF</th>
                <th>OOS Sharpe</th>
                <th>Win Rate</th>
                <th>Trades</th>
                <th>CV</th>
              </tr>
            </thead>
            <tbody>
              {combos.map((combo, i) => (
                <tr key={i}>
                  <td className="num">#{combo.rank}</td>
                  <td>{combo.bot}</td>
                  <td>{combo.timeframe}</td>
                  <td className="num">
                    {typeof combo.metrics.avg_sharpe === "number"
                      ? (combo.metrics.avg_sharpe as number).toFixed(2)
                      : "\u2014"}
                  </td>
                  <td className="num">
                    {typeof combo.metrics.avg_win_rate === "number"
                      ? `${((combo.metrics.avg_win_rate as number) * 100).toFixed(0)}%`
                      : "\u2014"}
                  </td>
                  <td className="num">{combo.metrics.total_trades as number ?? "\u2014"}</td>
                  <td className="num">
                    {typeof combo.metrics.sharpe_cv === "number"
                      ? (combo.metrics.sharpe_cv as number).toFixed(2)
                      : "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {recSet.status === "pending" && (
        <button
          className="opt-apply-btn recset-apply-btn"
          onClick={() => onApply(recSet.id)}
        >
          Apply to DEMO Allowlist
        </button>
      )}

      {recSet.status === "applied" && (
        <div className="recset-applied-badge">Applied {recSet.applied_at ? new Date(recSet.applied_at).toLocaleDateString() : ""}</div>
      )}
    </div>
  );
}

function GroupedAllowlistCard() {
  const [groups, setGroups] = useState<AllowlistGroup[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await engineClient.getGroupedAllowlist();
      setGroups(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load allowlist");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (isLoading) {
    return <div className="opt-loading">Loading allowlist...</div>;
  }

  if (error) {
    return (
      <div className="opt-error">
        <p className="opt-error-detail">{error}</p>
      </div>
    );
  }

  if (groups.length === 0) {
    return (
      <div className="opt-empty">
        <p className="opt-empty-title">Allowlist is empty</p>
        <p className="opt-empty-hint">
          Apply a recommended set above to populate the allowlist with validated
          strategy/symbol combinations. The allowlist controls which combos are
          available for autopilot trading.
        </p>
      </div>
    );
  }

  return (
    <div className="recset-combos">
      {groups.map((group) => (
        <div key={group.symbol} className="recset-symbol-group">
          <div className="combo-group-header">{group.symbol}</div>
          <table className="opt-combos-table">
            <thead>
              <tr>
                <th>Bot</th>
                <th>TF</th>
                <th>Enabled</th>
                <th>Sharpe</th>
                <th>Win Rate</th>
                <th>Trades</th>
                <th>Validated</th>
              </tr>
            </thead>
            <tbody>
              {group.bots.map((bot) => (
                <tr key={bot.combo_id} className={!bot.enabled ? "disabled-row" : ""}>
                  <td>{bot.bot}</td>
                  <td>{bot.timeframe}</td>
                  <td>{bot.enabled ? "Yes" : "No"}</td>
                  <td className="num">{bot.sharpe != null ? bot.sharpe.toFixed(2) : "\u2014"}</td>
                  <td className="num">
                    {bot.win_rate != null ? `${(bot.win_rate * 100).toFixed(0)}%` : "\u2014"}
                  </td>
                  <td className="num">{bot.total_trades ?? "\u2014"}</td>
                  <td>
                    {bot.validated_at
                      ? new Date(bot.validated_at).toLocaleDateString()
                      : "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

export function OptimizationScreen() {
  const {
    schedulerStatus,
    proposals,
    isLoading,
    error,
    refetch,
    applyProposal,
  } = useOptimization();
  const {
    latest: latestRec,
    all: allRecs,
    isLoading: recLoading,
    error: recError,
    applyDemo,
    refetch: refetchRecs,
  } = useRecommendations();
  const { showToast } = useToast();
  const [showWfoModal, setShowWfoModal] = useState(false);

  const handleApplyRec = useCallback(
    async (id: string) => {
      try {
        await applyDemo(id);
        showToast("Recommendation applied to allowlist", "success");
      } catch (err) {
        showToast(
          err instanceof Error ? err.message : "Failed to apply recommendation",
          "error"
        );
      }
    },
    [applyDemo, showToast]
  );

  if (isLoading) {
    return (
      <div className="opt-screen">
        <div className="opt-loading">Loading optimisation data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="opt-screen">
        <div className="opt-error">
          <p>Failed to load optimisation data</p>
          <p className="opt-error-detail">{error}</p>
          <button onClick={refetch} className="opt-retry-btn">
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="opt-screen">
      <h2 className="opt-title">Optimisation</h2>

      {/* Scheduler Status Card */}
      <div className="opt-card">
        <h3 className="opt-card-title">
          Scheduler
          <InfoTip text="The scheduler runs periodic jobs automatically. 'nightly_data_check' verifies data freshness every 24 hours. 'weekly_optimize' runs walk-forward optimisation every 7 days and generates proposals for the best strategy/symbol combinations." />
        </h3>
        <div className="opt-scheduler-status" style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              className={`opt-scheduler-dot ${schedulerStatus?.running ? "running" : "stopped"}`}
            />
            <span>{schedulerStatus?.running ? "Running" : "Stopped"}</span>
          </span>
          <button
            className="wizard-btn primary"
            style={{ padding: "4px 12px", fontSize: 12 }}
            onClick={() => setShowWfoModal(true)}
          >
            Run Walk-Forward Now
          </button>
        </div>

        {schedulerStatus?.jobs && (
          <div className="opt-jobs-grid">
            {Object.entries(schedulerStatus.jobs).map(([name, job]) => (
              <div key={name} className="opt-job-card">
                <div className="opt-job-name">{name.replace(/_/g, " ")}</div>
                <div className="opt-job-detail">
                  Interval: {job.interval_hours}h
                </div>
                <div className="opt-job-detail">
                  Runs: {job.run_count}
                </div>
                <div className="opt-job-detail">
                  Next:{" "}
                  {job.next_run
                    ? new Date(job.next_run).toLocaleString()
                    : "\u2014"}
                </div>
                {job.last_error && (
                  <div className="opt-job-error">{job.last_error}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recommended Set Card */}
      <div className="opt-card">
        <div className="opt-card-header">
          <h3 className="opt-card-title">
            Recommended Set
            <InfoTip text="Recommended sets are generated from walk-forward optimisation results using the combo selector. Each set contains the best-performing strategy/symbol/timeframe combinations, grouped by symbol. Apply a set to populate the DEMO allowlist for autopilot trading." />
          </h3>
          <button onClick={refetchRecs} className="opt-refresh-btn">
            Refresh
          </button>
        </div>

        {recLoading ? (
          <div className="opt-loading">Loading recommendations...</div>
        ) : recError && !latestRec ? (
          <div className="opt-error">
            <p className="opt-error-detail">{recError}</p>
          </div>
        ) : latestRec ? (
          <div className="recset-card">
            <div className="recset-header">
              <span className="recset-id">{latestRec.id}</span>
              <span className={`opt-proposal-status opt-status-${latestRec.status}`}>
                {latestRec.status}
              </span>
              <span className="recset-meta">
                {latestRec.combos.length} combos | {latestRec.rejected_count} rejected
              </span>
              <span className="recset-meta">
                {new Date(latestRec.generated_at).toLocaleDateString()}
              </span>
            </div>
            <GroupedComboList recSet={latestRec} onApply={handleApplyRec} />
          </div>
        ) : (
          <div className="opt-empty">
            <p className="opt-empty-title">No recommended set yet</p>
            <p className="opt-empty-hint">
              Run a walk-forward optimisation first, then use the &ldquo;Generate&rdquo;
              endpoint or wait for the scheduler to create a recommended set automatically.
              The selector filters, ranks, and diversifies combos from your WFO results.
            </p>
          </div>
        )}

        {allRecs.length > 1 && (
          <details className="recset-history">
            <summary>{allRecs.length} recommendation sets total</summary>
            <ul className="recset-history-list">
              {allRecs.map((rs) => (
                <li key={rs.id} className="recset-history-item">
                  <span className="recset-id">{rs.id}</span>
                  <span className={`opt-proposal-status opt-status-${rs.status}`}>{rs.status}</span>
                  <span>{rs.combos_count} combos</span>
                  <span>{new Date(rs.generated_at).toLocaleDateString()}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {/* Active Allowlist */}
      <div className="opt-card">
        <h3 className="opt-card-title">
          Active Allowlist
          <InfoTip text="The current allowlist controls which bot/symbol/timeframe combinations are available for autopilot trading. Entries are grouped by symbol. Apply a recommended set to update the allowlist." />
        </h3>
        <GroupedAllowlistCard />
      </div>

      {/* Proposals Table */}
      <div className="opt-card">
        <div className="opt-card-header">
          <h3 className="opt-card-title">
            Proposals
            <InfoTip text="Proposals are generated by walk-forward optimisation. Each proposal recommends strategy/symbol combinations that performed well out-of-sample. Proposals are never auto-applied. Review the metrics and click 'Apply' to add them to your allowlist (DEMO mode only)." />
          </h3>
          <button onClick={refetch} className="opt-refresh-btn">
            Refresh
          </button>
        </div>

        {proposals.length === 0 ? (
          <div className="opt-empty">
            <p className="opt-empty-title">No proposals yet</p>
            <p className="opt-empty-hint">
              Proposals are created when the weekly optimisation job runs, or when you
              manually trigger a walk-forward optimisation. The scheduler will generate
              proposals automatically once it has enough historical data.
            </p>
          </div>
        ) : (
          <div className="opt-proposals-list">
            {proposals.map((p) => (
              <ProposalRow
                key={p.proposal_id}
                proposal={p}
                onApply={applyProposal}
              />
            ))}
          </div>
        )}
      </div>

      {/* WFO Trigger Modal */}
      {showWfoModal && (
        <WfoTriggerModal
          onClose={() => setShowWfoModal(false)}
          onComplete={() => {
            setShowWfoModal(false);
            refetch();
          }}
        />
      )}
    </div>
  );
}
