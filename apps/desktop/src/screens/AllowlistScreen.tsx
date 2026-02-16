/**
 * Allowlist Manager — source of truth for trading combos (bot + symbol + TF).
 *
 * Features:
 * - View all allowlist entries grouped by symbol
 * - Toggle enable/disable per combo
 * - Bulk actions: enable selected, disable all
 * - Metrics per combo: Sharpe, win rate, drawdown, trades
 * - Filter/search combos
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import { SummaryBar } from "../components/ui/SummaryBar";
import { Panel } from "../components/ui/Panel";
import { EmptyState } from "../components/ui/EmptyState";
import { useEngineConnection } from "../context/EngineConnectionContext";
import { engineClient, AllowlistEntry } from "../lib/engineClient";
import { CATEGORIES, getBotById } from "../lib/elite8Meta";

type SortField = "symbol" | "bot" | "timeframe" | "sharpe" | "win_rate" | "total_trades";
type SortDir = "asc" | "desc";

export function AllowlistScreen() {
  const { health } = useEngineConnection();
  const [entries, setEntries] = useState<AllowlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sortField, setSortField] = useState<SortField>("symbol");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const fetchEntries = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await engineClient.getAllowlistEntries();
      setEntries(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load allowlist");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  const toggleSelect = useCallback((comboId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(comboId)) next.delete(comboId);
      else next.add(comboId);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelected(new Set(filteredEntries.map((e) => e.combo_id)));
  }, []);

  const clearSelection = useCallback(() => {
    setSelected(new Set());
  }, []);

  const filteredEntries = useMemo(() => {
    let list = entries;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (e) =>
          e.symbol.toLowerCase().includes(q) ||
          e.bot.toLowerCase().includes(q) ||
          e.timeframe.toLowerCase().includes(q)
      );
    }
    list = [...list].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === "string" && typeof bVal === "string") return aVal.localeCompare(bVal) * dir;
      return ((aVal as number) - (bVal as number)) * dir;
    });
    return list;
  }, [entries, search, sortField, sortDir]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  const sortIndicator = (field: SortField) => {
    if (sortField !== field) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  };

  const enabledCount = entries.filter((e) => e.enabled).length;

  const getCategoryForBot = (botId: string) => {
    const meta = getBotById(botId);
    if (!meta) return null;
    return CATEGORIES[meta.category];
  };

  return (
    <div className="screen-layout">
      <SummaryBar
        pageId="allowlist"
        title="Allowlist Manager"
        description="Source of truth for trading combos. Each entry is a bot + symbol + timeframe combination that can be enabled for live/paper trading via Autopilot."
        actions={[
          "Toggle combos on/off to control what Autopilot trades",
          "Use bulk actions to enable/disable multiple combos at once",
          "Review Sharpe and win rate before enabling a combo",
        ]}
        chips={[
          { label: "Total", value: `${entries.length}`, variant: "info" },
          { label: "Enabled", value: `${enabledCount}`, variant: enabledCount > 0 ? "success" : "default" },
          { label: "Engine", value: health?.status === "healthy" ? "Online" : "Offline",
            variant: health?.status === "healthy" ? "success" : "danger" },
        ]}
      />

      <div className="screen-content">
        {/* Toolbar */}
        <div className="allowlist-toolbar">
          <input
            className="ui-input"
            type="text"
            placeholder="Search symbol, bot, or timeframe..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ maxWidth: 280 }}
          />
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {selected.size > 0 && (
              <>
                <span className="badge badge-muted">{selected.size} selected</span>
                <button className="btn btn-sm" onClick={clearSelection}>
                  Clear
                </button>
              </>
            )}
            <button className="btn btn-sm" onClick={selectAll}>
              Select All
            </button>
            <button className="btn btn-sm btn-primary" onClick={fetchEntries}>
              Refresh
            </button>
          </div>
        </div>

        {loading ? (
          <EmptyState
            title="Loading allowlist..."
            description="Fetching trading combos from engine."
          />
        ) : error ? (
          <EmptyState
            title="Failed to load allowlist"
            description={error}
            actionLabel="Retry"
            onAction={fetchEntries}
          />
        ) : filteredEntries.length === 0 ? (
          <EmptyState
            title={search ? "No matching combos" : "Allowlist is empty"}
            description={
              search
                ? `No combos match "${search}". Try a different search.`
                : "Run the Optimise pipeline to generate recommended combos, or add entries manually."
            }
          />
        ) : (
          <Panel scrollable noPad>
            <table className="ui-table">
              <thead>
                <tr>
                  <th style={{ width: 32 }}>
                    <input
                      type="checkbox"
                      checked={selected.size === filteredEntries.length && filteredEntries.length > 0}
                      onChange={() => {
                        if (selected.size === filteredEntries.length) clearSelection();
                        else selectAll();
                      }}
                    />
                  </th>
                  <th className="sortable" onClick={() => handleSort("symbol")}>
                    Symbol{sortIndicator("symbol")}
                  </th>
                  <th className="sortable" onClick={() => handleSort("bot")}>
                    Bot{sortIndicator("bot")}
                  </th>
                  <th className="sortable" onClick={() => handleSort("timeframe")}>
                    TF{sortIndicator("timeframe")}
                  </th>
                  <th className="sortable num" onClick={() => handleSort("sharpe")}>
                    Sharpe{sortIndicator("sharpe")}
                  </th>
                  <th className="sortable num" onClick={() => handleSort("win_rate")}>
                    Win %{sortIndicator("win_rate")}
                  </th>
                  <th className="num">DD %</th>
                  <th className="sortable num" onClick={() => handleSort("total_trades")}>
                    Trades{sortIndicator("total_trades")}
                  </th>
                  <th style={{ width: 80 }}>Status</th>
                  <th style={{ width: 100 }}>Validated</th>
                </tr>
              </thead>
              <tbody>
                {filteredEntries.map((entry) => {
                  const cat = getCategoryForBot(entry.bot);
                  return (
                    <tr
                      key={entry.combo_id}
                      className={selected.has(entry.combo_id) ? "row-selected" : ""}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={selected.has(entry.combo_id)}
                          onChange={() => toggleSelect(entry.combo_id)}
                        />
                      </td>
                      <td style={{ fontFamily: "var(--font-mono)", fontWeight: 500 }}>{entry.symbol}</td>
                      <td>
                        <span className="bot-name-inline">{entry.bot}</span>
                        {cat && (
                          <span
                            className="badge"
                            style={{ background: cat.bg, color: cat.text, marginLeft: 6, fontSize: 9 }}
                          >
                            {cat.label}
                          </span>
                        )}
                      </td>
                      <td className="num">{entry.timeframe}</td>
                      <td className="num">
                        {entry.sharpe != null ? (
                          <span className={entry.sharpe >= 1 ? "text-green" : entry.sharpe < 0 ? "text-red" : ""}>
                            {entry.sharpe.toFixed(2)}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="num">
                        {entry.win_rate != null ? `${(entry.win_rate * 100).toFixed(1)}%` : "—"}
                      </td>
                      <td className="num">
                        {entry.max_drawdown_pct != null ? (
                          <span className={entry.max_drawdown_pct > 10 ? "text-red" : ""}>
                            {entry.max_drawdown_pct.toFixed(1)}%
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="num">{entry.total_trades}</td>
                      <td>
                        <span className={`badge ${entry.enabled ? "badge-green" : "badge-muted"}`}>
                          {entry.enabled ? "Enabled" : "Disabled"}
                        </span>
                      </td>
                      <td style={{ fontSize: 10, color: "var(--text-muted)" }}>
                        {entry.validated_at
                          ? new Date(entry.validated_at).toLocaleDateString()
                          : "Never"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Panel>
        )}
      </div>
    </div>
  );
}
