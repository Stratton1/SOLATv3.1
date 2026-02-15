/**
 * Bots & Strategies page — list/grid of available trading bots.
 *
 * Features:
 * - Bot cards with name, description, category, warmup bars
 * - Toggle starred/favourites
 * - Filter views: Starred, All
 * - Bot detail drawer (click to expand)
 */

import { useState, useMemo, useCallback } from "react";
import { SummaryBar } from "../components/ui/SummaryBar";
import { EmptyState } from "../components/ui/EmptyState";
import { ELITE_8_BOTS, CATEGORIES, BotMeta } from "../lib/elite8Meta";
import { useEngineHealth } from "../hooks/useEngineHealth";

type BotView = "all" | "starred" | "trend" | "momentum" | "reversal" | "breakout";

const STARRED_KEY = "solat_starred_bots";

function getStarred(): Set<string> {
  try {
    const raw = localStorage.getItem(STARRED_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw));
  } catch {
    return new Set();
  }
}

function saveStarred(set: Set<string>) {
  try {
    localStorage.setItem(STARRED_KEY, JSON.stringify([...set]));
  } catch {
    // ignore
  }
}

export function BotsScreen() {
  const { health } = useEngineHealth();
  const [view, setView] = useState<BotView>("all");
  const [starred, setStarred] = useState<Set<string>>(getStarred);
  const [selectedBot, setSelectedBot] = useState<BotMeta | null>(null);

  const toggleStar = useCallback((id: string) => {
    setStarred((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      saveStarred(next);
      return next;
    });
  }, []);

  const filteredBots = useMemo(() => {
    if (view === "starred") return ELITE_8_BOTS.filter((b) => starred.has(b.id));
    if (view === "all") return ELITE_8_BOTS;
    return ELITE_8_BOTS.filter((b) => b.category === view);
  }, [view, starred]);

  return (
    <div className="screen-layout">
      <SummaryBar
        pageId="bots"
        title="Bots & Strategies"
        description="View and manage the Elite 8 trading strategies. Each bot uses Ichimoku-based technical analysis with unique entry/exit logic."
        actions={[
          "Star your favourite bots for quick access",
          "Click a bot to see its parameters and description",
          "Filter by category to compare similar strategies",
        ]}
        chips={[
          { label: "Bots", value: `${ELITE_8_BOTS.length}`, variant: "info" },
          { label: "Engine", value: health?.status === "healthy" ? "Online" : "Offline",
            variant: health?.status === "healthy" ? "success" : "danger" },
        ]}
      />

      <div className="screen-content">
        {/* View tabs */}
        <div className="ui-tabs" style={{ marginBottom: 16 }}>
          {(["all", "starred", "trend", "momentum", "reversal", "breakout"] as BotView[]).map((v) => (
            <button
              key={v}
              className={`ui-tab ${view === v ? "active" : ""}`}
              onClick={() => setView(v)}
            >
              {v === "all" ? "All" : v === "starred" ? `Starred (${starred.size})` : CATEGORIES[v]?.label ?? v}
            </button>
          ))}
        </div>

        {filteredBots.length === 0 ? (
          <EmptyState
            title={view === "starred" ? "No starred bots" : "No bots in this category"}
            description={view === "starred"
              ? "Click the star icon on any bot to add it to your favourites."
              : "Try a different filter."}
          />
        ) : (
          <div className="bots-grid">
            {filteredBots.map((bot) => (
              <div
                key={bot.id}
                className="bot-card"
                onClick={() => setSelectedBot(selectedBot?.id === bot.id ? null : bot)}
              >
                <div className="bot-card-header">
                  <span className="bot-card-name">{bot.name}</span>
                  <button
                    className={`bot-card-star ${starred.has(bot.id) ? "starred" : ""}`}
                    onClick={(e) => { e.stopPropagation(); toggleStar(bot.id); }}
                    aria-label={starred.has(bot.id) ? "Unstar" : "Star"}
                  >
                    {starred.has(bot.id) ? "★" : "☆"}
                  </button>
                </div>
                <p className="bot-card-desc">{bot.description}</p>
                <div className="bot-card-meta">
                  <span className="badge" style={{
                    background: CATEGORIES[bot.category].bg,
                    color: CATEGORIES[bot.category].text,
                  }}>
                    {CATEGORIES[bot.category].label}
                  </span>
                  <span className="badge badge-muted">Warmup: {bot.warmupBars} bars</span>
                  <span className="badge badge-muted">{bot.params.length} params</span>
                </div>

                {/* Expanded detail */}
                {selectedBot?.id === bot.id && (
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border-light)" }}>
                    <p style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 6 }}>
                      Parameters
                    </p>
                    {bot.params.length === 0 ? (
                      <p style={{ fontSize: 11, color: "var(--text-muted)" }}>No configurable parameters</p>
                    ) : (
                      <table className="ui-table" style={{ fontSize: 11 }}>
                        <thead>
                          <tr>
                            <th>Name</th>
                            <th>Default</th>
                            <th>Range</th>
                            <th>Description</th>
                          </tr>
                        </thead>
                        <tbody>
                          {bot.params.map((p) => (
                            <tr key={p.name}>
                              <td style={{ fontFamily: "var(--font-mono)" }}>{p.name}</td>
                              <td className="num">{String(p.default)}</td>
                              <td className="num">
                                {p.min != null && p.max != null ? `${p.min}–${p.max}` : "—"}
                              </td>
                              <td>{p.description}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
