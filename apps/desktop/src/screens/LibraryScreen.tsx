/**
 * Library Screen — Data Explorer with Bars / Backtests / Sweeps tabs.
 */

import { useState } from "react";
import { open } from "@tauri-apps/plugin-shell";
import { useArtefactIndex, ArtefactIndex } from "../hooks/useArtefactIndex";

type TabKey = "bars" | "backtests" | "sweeps";

export function LibraryScreen() {
  const { data, isLoading, error, refetch } = useArtefactIndex();
  const [tab, setTab] = useState<TabKey>("bars");
  const [filter, setFilter] = useState("");

  const filterLower = filter.toLowerCase();

  const renderBars = (data: ArtefactIndex) => {
    const rows = data.bars.filter(
      (b) =>
        b.symbol.toLowerCase().includes(filterLower) ||
        b.timeframe.toLowerCase().includes(filterLower),
    );
    if (rows.length === 0) return <div className="library-empty">No bars data found.</div>;
    return (
      <table className="library-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Timeframe</th>
            <th>Bars</th>
            <th>Start</th>
            <th>End</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b, i) => (
            <tr key={`${b.symbol}-${b.timeframe}-${i}`}>
              <td className="mono">{b.symbol}</td>
              <td>{b.timeframe}</td>
              <td className="num">{b.row_count?.toLocaleString()}</td>
              <td className="mono">{b.start_ts?.split("T")[0] ?? "\u2014"}</td>
              <td className="mono">{b.end_ts?.split("T")[0] ?? "\u2014"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  const renderBacktests = (data: ArtefactIndex) => {
    const rows = data.backtests.filter(
      (b) =>
        (b.run_id ?? "").toLowerCase().includes(filterLower) ||
        (b.bots ?? []).some((bot: string) => bot.toLowerCase().includes(filterLower)) ||
        (b.symbols ?? []).some((sym: string) => sym.toLowerCase().includes(filterLower)),
    );
    if (rows.length === 0)
      return <div className="library-empty">No backtest runs found.</div>;
    return (
      <table className="library-table">
        <thead>
          <tr>
            <th>Run ID</th>
            <th>Created</th>
            <th>Symbols</th>
            <th>Bots</th>
            <th>TF</th>
            <th>Sharpe</th>
            <th>Trades</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.run_id}>
              <td className="mono">{b.run_id?.slice(0, 12) ?? "\u2014"}</td>
              <td className="mono">{b.created_at?.split("T")[0] ?? "\u2014"}</td>
              <td>{(b.symbols ?? []).join(", ")}</td>
              <td>{(b.bots ?? []).join(", ")}</td>
              <td>{b.timeframe ?? "\u2014"}</td>
              <td className="num">{b.sharpe != null ? Number(b.sharpe).toFixed(2) : "\u2014"}</td>
              <td className="num">{b.total_trades ?? 0}</td>
              <td>
                {b.path && (
                  <button className="btn-inline" onClick={() => open(b.path!)}>
                    Open
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  const renderSweeps = (data: ArtefactIndex) => {
    const rows = data.sweeps.filter(
      (s) =>
        (s.sweep_id ?? "").toLowerCase().includes(filterLower) ||
        (s.scope ?? "").toLowerCase().includes(filterLower),
    );
    if (rows.length === 0)
      return <div className="library-empty">No sweep results found.</div>;
    return (
      <table className="library-table">
        <thead>
          <tr>
            <th>Sweep ID</th>
            <th>Scope</th>
            <th>Combos</th>
            <th>Top Sharpe</th>
            <th>Date</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.sweep_id}>
              <td className="mono">{s.sweep_id?.slice(0, 20) ?? "\u2014"}</td>
              <td>{s.scope ?? "\u2014"}</td>
              <td className="num">{s.total_combos ?? 0}</td>
              <td className="num">
                {s.top_sharpe != null ? Number(s.top_sharpe).toFixed(2) : "\u2014"}
              </td>
              <td className="mono">{s.generated_at?.split("T")[0] ?? "\u2014"}</td>
              <td>
                {s.path && (
                  <button className="btn-inline" onClick={() => open(s.path!)}>
                    Open
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  return (
    <div className="library-screen">
      <div className="library-header">
        <h2 className="status-title">Library</h2>
        <button className="opt-refresh-btn" onClick={refetch}>
          Refresh
        </button>
      </div>

      <div className="library-tabs">
        {(["bars", "backtests", "sweeps"] as TabKey[]).map((t) => (
          <button
            key={t}
            className={`library-tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <input
        type="text"
        className="library-search"
        placeholder="Filter..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      <div className="library-content">
        {isLoading && <div className="library-loading">Loading artefacts...</div>}
        {error && <div className="library-error">Error: {error}</div>}
        {data && !isLoading && (
          <>
            {tab === "bars" && renderBars(data)}
            {tab === "backtests" && renderBacktests(data)}
            {tab === "sweeps" && renderSweeps(data)}
          </>
        )}
      </div>
    </div>
  );
}

export default LibraryScreen;
