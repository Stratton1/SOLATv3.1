/**
 * Data Library card — Bars / Sweeps tabs for the System dashboard.
 * Extracted from LibraryScreen with Quick Sync + Derive actions.
 */

import { useState } from "react";
import { open } from "@tauri-apps/plugin-shell";
import { useArtefactIndex, ArtefactIndex } from "../../hooks/useArtefactIndex";
import { engineClient } from "../../lib/engineClient";
import { useToast } from "../../context/ToastContext";

type TabKey = "bars" | "sweeps";

export function DataLibraryCard() {
  const { data, isLoading, error, refetch } = useArtefactIndex();
  const { showToast } = useToast();
  const [tab, setTab] = useState<TabKey>("bars");
  const [filter, setFilter] = useState("");
  const [syncing, setSyncing] = useState(false);

  const handleQuickSync = async () => {
    setSyncing(true);
    try {
      const res = await engineClient.quickSync(30);
      showToast(res.ok ? `Synced ${res.per_symbol_results?.length ?? 0} symbols` : "Sync failed", res.ok ? "success" : "error");
      refetch();
    } catch {
      showToast("Sync failed — engine offline?", "error");
    } finally {
      setSyncing(false);
    }
  };

  const handleDeriveAll = async () => {
    setSyncing(true);
    try {
      const res = await engineClient.deriveAll();
      showToast(
        res.ok
          ? `Derived ${res.target_timeframes.join(", ")} for ${res.total_symbols} symbols`
          : "Derive failed",
        res.ok ? "success" : "error",
      );
      refetch();
    } catch {
      showToast("Derive failed — engine offline?", "error");
    } finally {
      setSyncing(false);
    }
  };

  const filterLower = filter.toLowerCase();

  const totalBars = data?.bars.reduce((sum, b) => sum + (b.row_count ?? 0), 0) ?? 0;
  const totalSymbols = data ? new Set(data.bars.map((b) => b.symbol)).size : 0;

  return (
    <div className="terminal-card" style={{ flex: "1 1 auto", minHeight: 0 }}>
      <div className="terminal-card-header">
        <span className="terminal-card-title">Data Library</span>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <button className="btn-inline" disabled={syncing} onClick={handleQuickSync}>
            {syncing ? "Syncing..." : "Sync 30d"}
          </button>
          <button className="btn-inline" disabled={syncing} onClick={handleDeriveAll}>
            Derive
          </button>
          <button className="btn-inline" onClick={refetch}>Refresh</button>
        </div>
      </div>
      <div className="terminal-card-body" style={{ display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
        {/* Summary strip */}
        <div className="dense-row" style={{ marginBottom: 6 }}>
          <span className="dense-label">Symbols</span>
          <span className="dense-value num">{totalSymbols}</span>
          <span className="dense-label" style={{ marginLeft: 12 }}>Bars</span>
          <span className="dense-value num">{totalBars.toLocaleString()}</span>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
          {(["bars", "sweeps"] as TabKey[]).map((t) => (
            <button
              key={t}
              className={`blotter-tab ${tab === t ? "active" : ""}`}
              onClick={() => setTab(t)}
              style={{ fontSize: 10, padding: "3px 8px" }}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
          <input
            type="text"
            placeholder="Filter..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{
              marginLeft: "auto",
              fontSize: 10,
              padding: "2px 6px",
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-primary)",
              width: 120,
            }}
          />
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
          {isLoading && <div style={{ padding: 12, color: "var(--text-muted)", fontSize: 11 }}>Loading...</div>}
          {error && <div style={{ padding: 12, color: "var(--accent-red)", fontSize: 11 }}>Error: {error}</div>}
          {data && !isLoading && tab === "bars" && <BarsTable data={data} filter={filterLower} />}
          {data && !isLoading && tab === "sweeps" && <SweepsTable data={data} filter={filterLower} />}
        </div>
      </div>
    </div>
  );
}

function BarsTable({ data, filter }: { data: ArtefactIndex; filter: string }) {
  const rows = data.bars.filter(
    (b) => b.symbol.toLowerCase().includes(filter) || b.timeframe.toLowerCase().includes(filter),
  );
  if (rows.length === 0) return <div style={{ padding: 12, color: "var(--text-muted)", fontSize: 11 }}>No bars data.</div>;
  return (
    <table className="library-table" style={{ fontSize: 10 }}>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>TF</th>
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
}

function SweepsTable({ data, filter }: { data: ArtefactIndex; filter: string }) {
  const rows = data.sweeps.filter(
    (s) => (s.sweep_id ?? "").toLowerCase().includes(filter) || (s.scope ?? "").toLowerCase().includes(filter),
  );
  if (rows.length === 0) return <div style={{ padding: 12, color: "var(--text-muted)", fontSize: 11 }}>No sweeps.</div>;
  return (
    <table className="library-table" style={{ fontSize: 10 }}>
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
            <td className="mono">{s.sweep_id?.slice(0, 16) ?? "\u2014"}</td>
            <td>{s.scope ?? "\u2014"}</td>
            <td className="num">{s.total_combos ?? 0}</td>
            <td className="num">{s.top_sharpe != null ? Number(s.top_sharpe).toFixed(2) : "\u2014"}</td>
            <td className="mono">{s.generated_at?.split("T")[0] ?? "\u2014"}</td>
            <td>
              {s.path && (
                <button className="btn-inline" onClick={() => open(s.path!)}>Open</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
