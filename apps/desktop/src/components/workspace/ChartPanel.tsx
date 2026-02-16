/**
 * ChartPanel - individual chart panel within workspace grid.
 *
 * Contains:
 * - Panel header with symbol/timeframe selectors + zoom buttons
 * - Live/HIST badge
 * - Overflow menu for toggles (signals, indicators, exec, SL/TP, drawings)
 * - CandleChart with markers, SL/TP zones, executions
 * - Quick Trade overlay (BUY/SELL)
 * - Focus mode maximize button
 */

import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import Plotly from "plotly.js-finance-dist";
import { CandleChart } from "../CandleChart";
import { DrawingToolbar } from "../DrawingToolbar";
import { ContextMenu, useContextMenu, type ContextMenuItem } from "../ContextMenu";
import { StrategyPopover } from "./StrategyPopover";
import { IndicatorPopover } from "./IndicatorPopover";
import { MarketBrowser } from "./MarketBrowser";
import { useBars } from "../../hooks/useBars";
import { useOverlays } from "../../hooks/useOverlays";
import { useSignals } from "../../hooks/useSignals";
import { useCatalogue } from "../../hooks/useCatalogue";
import { useWorkspace } from "../../hooks/useWorkspace";
import { useWsEvents, QuoteUpdateEvent, BarUpdateEvent } from "../../hooks/useWsEvents";
import { useExecutionEvents } from "../../hooks/useExecutionEvents";
import { useDrawings } from "../../hooks/useDrawings";
import {
  Panel,
  PanelBot,
  PanelIndicator,
  TIMEFRAMES,
  LinkGroup,
  getMinimumLookbackBars,
} from "../../lib/workspace";
import { Drawing, DEFAULT_DRAWING_COLOR } from "../../lib/drawings";
import { engineClient } from "../../lib/engineClient";
import { useToast } from "../../context/ToastContext";

// =============================================================================
// Types
// =============================================================================

interface ChartPanelProps {
  panel: Panel;
  index: number;
  isOnlyPanel?: boolean;
  onMaximize?: (panelId: string) => void;
  canMaximize?: boolean;
}

const LINK_GROUPS: LinkGroup[] = ["none", "A", "B", "C"];

// Zoom presets in bars per timeframe period
const ZOOM_PRESETS = [
  { label: "1D", hours: 24 },
  { label: "1W", hours: 168 },
  { label: "1M", hours: 720 },
  { label: "3M", hours: 2160 },
  { label: "ALL", hours: 0 },
] as const;

// =============================================================================
// Component
// =============================================================================

export function ChartPanel({
  panel,
  index: _index,
  isOnlyPanel = false,
  onMaximize,
  canMaximize = false,
}: ChartPanelProps) {
  const { updatePanel, setLinkedTimeframe, setLinkedSymbol } = useWorkspace();
  const { items: catalogueItems } = useCatalogue();
  const { showToast } = useToast();

  // Local state
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [quote, setQuote] = useState<QuoteUpdateEvent | null>(null);
  const [showStrategyPopover, setShowStrategyPopover] = useState(false);
  const [showIndicatorPopover, setShowIndicatorPopover] = useState(false);
  const [isTrading, setIsTrading] = useState(false);
  const [showOverflowMenu, setShowOverflowMenu] = useState(false);
  const [showDrawingToolbar, setShowDrawingToolbar] = useState(false);
  const [showRangeSlider, setShowRangeSlider] = useState(false);
  const [showMarketBrowser, setShowMarketBrowser] = useState(false);
  const [activeZoom, setActiveZoom] = useState<string | null>(null);
  const [xRange, setXRange] = useState<[string, string] | null>(null);
  const [hasManualRange, setHasManualRange] = useState(false);
  const [historyLimitReached, setHistoryLimitReached] = useState(false);
  const overflowRef = useRef<HTMLDivElement>(null);
  const symbolDropdownRef = useRef<HTMLDivElement>(null);
  const marketBrowserRef = useRef<HTMLDivElement>(null);

  // Data hooks
  const {
    bars,
    isLoading: barsLoading,
    isLoadingHistory,
    start: barsStart,
    end: barsEnd,
    requestedLimit,
    coveragePct,
    source,
    hasMoreHistory,
    appendBar,
    loadOlderBars,
  } = useBars({
    symbol: panel.symbol,
    timeframe: panel.timeframe,
    limit: Math.max(panel.lookbackBars, getMinimumLookbackBars(panel.timeframe)),
  });

  const enabledIndicators = useMemo(
    () => panel.indicators.filter((i) => i.enabled),
    [panel.indicators]
  );

  // Only fetch overlays for focused panel or single panel
  const shouldFetchOverlays = isFocused || isOnlyPanel;

  const { overlays } = useOverlays({
    symbol: panel.symbol,
    timeframe: panel.timeframe,
    indicators: shouldFetchOverlays ? enabledIndicators : [],
  });

  const enabledBots = useMemo(
    () => panel.bots.filter((b) => b.enabled).map((b) => b.id),
    [panel.bots]
  );
  const shouldFetchSignals = panel.showMarkers && enabledBots.length > 0 && (isFocused || isOnlyPanel);
  const { signals } = useSignals({
    symbol: panel.symbol,
    timeframe: panel.timeframe,
    strategies: enabledBots,
    enabled: shouldFetchSignals,
    debounceMs: 500,
  });

  // Execution markers + SL/TP levels
  const showExec = panel.showExecutions !== false;
  const showSlTp = panel.showSlTp !== false;
  const { executions, slTpLevels } = useExecutionEvents({
    symbol: panel.symbol,
    enabled: showExec || showSlTp,
  });

  // Drawings
  const {
    chartDrawings,
    activeTool,
    setActiveTool,
    addDrawing,
    clearDrawings,
  } = useDrawings({
    panelId: panel.id,
    symbol: panel.symbol,
    timeframe: panel.timeframe,
  });

  // Context menu
  const { menu, showContextMenu, closeContextMenu } = useContextMenu();

  // WebSocket handlers
  const handleQuote = useCallback(
    (event: QuoteUpdateEvent) => {
      if (event.symbol === panel.symbol) {
        setQuote(event);
      }
    },
    [panel.symbol]
  );

  const handleBar = useCallback(
    (event: BarUpdateEvent) => {
      if (event.symbol === panel.symbol && event.timeframe === panel.timeframe) {
        appendBar(event.bar);
      }
    },
    [panel.symbol, panel.timeframe, appendBar]
  );

  useWsEvents({
    onQuote: handleQuote,
    onBar: handleBar,
  });

  // Quote polling fallback (normalized route-only flow).
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await engineClient.getQuotes([panel.symbol]);
        if (cancelled) return;
        const next = res.quotes[panel.symbol];
        if (next) {
          setQuote({
            type: "quote_update",
            symbol: next.symbol,
            bid: next.bid,
            ask: next.ask,
            mid: next.mid,
            ts: next.ts,
          });
        }
      } catch {
        // Keep existing quote if polling fails.
      }
    };
    poll();
    const interval = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [panel.symbol]);

  // Handle deep link from blotter/palette (sessionStorage) — run once on mount
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("solat_chart_deeplink");
      if (!raw) return;
      const link = JSON.parse(raw) as { symbol: string; timeframe?: string; timestamp?: string };
      sessionStorage.removeItem("solat_chart_deeplink");

      // Only handle on the first panel
      if (_index !== 0) return;

      if (link.symbol && link.symbol !== panel.symbol) {
        handleSymbolChange(link.symbol);
      }
      if (link.timeframe && link.timeframe !== panel.timeframe) {
        handleTimeframeChange(link.timeframe);
      }
    } catch {
      // Ignore parse errors
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Close overflow menu on outside click
  useEffect(() => {
    if (!showOverflowMenu) return;
    const handleClick = (e: MouseEvent) => {
      if (overflowRef.current && !overflowRef.current.contains(e.target as Node)) {
        setShowOverflowMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showOverflowMenu]);

  // Close symbol dropdown on outside click (without global backdrop intercepting clicks)
  useEffect(() => {
    if (!showSymbolDropdown) return;
    const handleClick = (e: MouseEvent) => {
      if (symbolDropdownRef.current && !symbolDropdownRef.current.contains(e.target as Node)) {
        setShowSymbolDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showSymbolDropdown]);

  // Close market browser on outside click
  useEffect(() => {
    if (!showMarketBrowser) return;
    const handleClick = (e: MouseEvent) => {
      if (marketBrowserRef.current && !marketBrowserRef.current.contains(e.target as Node)) {
        setShowMarketBrowser(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showMarketBrowser]);

  // Clear zoom when symbol/timeframe changes
  useEffect(() => {
    setActiveZoom(null);
    setXRange(null);
    setHasManualRange(false);
    setHistoryLimitReached(false);
  }, [panel.symbol, panel.timeframe]);

  const effectiveXRange = useMemo<[string, string] | null>(() => {
    if (xRange) return xRange;
    if (hasManualRange) return null;
    if (bars.length < 2) return null;
    return [bars[0].ts, bars[bars.length - 1].ts];
  }, [xRange, hasManualRange, bars]);

  // Filter symbols for search
  const filteredSymbols = useMemo(() => {
    const query = symbolSearch.toLowerCase();
    return catalogueItems.filter(
      (item) =>
        item.symbol.toLowerCase().includes(query) ||
        item.display_name.toLowerCase().includes(query)
    );
  }, [catalogueItems, symbolSearch]);

  // Handlers
  const handleSymbolChange = useCallback(
    (symbol: string) => {
      const normalizedSymbol = symbol.toUpperCase();
      updatePanel(panel.id, { symbol: normalizedSymbol });
      if (panel.linkGroup !== "none") {
        setLinkedSymbol(panel.linkGroup, normalizedSymbol);
      }
      setShowSymbolDropdown(false);
      setSymbolSearch("");
    },
    [panel.id, panel.linkGroup, updatePanel, setLinkedSymbol]
  );

  const handleTimeframeChange = useCallback(
    (timeframe: string) => {
      updatePanel(panel.id, { timeframe });
      if (panel.linkGroup !== "none") {
        setLinkedTimeframe(panel.linkGroup, timeframe);
      }
    },
    [panel.id, panel.linkGroup, updatePanel, setLinkedTimeframe]
  );

  const handleLinkGroupChange = useCallback(
    (linkGroup: LinkGroup) => {
      updatePanel(panel.id, { linkGroup });
    },
    [panel.id, updatePanel]
  );

  const handleBotsUpdate = useCallback(
    (bots: PanelBot[]) => {
      updatePanel(panel.id, { bots, showMarkers: true });
    },
    [panel.id, updatePanel]
  );

  const handleIndicatorsUpdate = useCallback(
    (indicators: PanelIndicator[]) => {
      updatePanel(panel.id, { indicators });
    },
    [panel.id, updatePanel]
  );

  const toggleSlTp = useCallback(() => {
    updatePanel(panel.id, { showSlTp: !(panel.showSlTp !== false) });
  }, [panel.id, panel.showSlTp, updatePanel]);

  const toggleExecutions = useCallback(() => {
    updatePanel(panel.id, { showExecutions: !(panel.showExecutions !== false) });
  }, [panel.id, panel.showExecutions, updatePanel]);

  // 2E: Quick zoom handler
  const handleZoom = useCallback(
    (preset: typeof ZOOM_PRESETS[number]) => {
      if (preset.hours === 0) {
        // ALL — clear range, let Plotly autorange
        setActiveZoom("ALL");
        setXRange(null);
        return;
      }

      if (bars.length === 0) return;

      const lastBarTime = new Date(bars[bars.length - 1].ts);
      const startTime = new Date(lastBarTime.getTime() - preset.hours * 3600 * 1000);
      setActiveZoom(preset.label);
      setXRange([startTime.toISOString(), lastBarTime.toISOString()]);
    },
    [bars]
  );

  // 2A: Handle relayout — manual pan clears active zoom preset
  const handleRelayout = useCallback(
    async (event: Plotly.PlotRelayoutEvent) => {
      // User panned/zoomed manually — clear zoom preset
      if (event["xaxis.range[0]"] || event["xaxis.range[1]"] || event["xaxis.autorange"]) {
        setActiveZoom(null);
      }
      if (event["xaxis.range[0]"] || event["xaxis.range[1]"]) {
        setHasManualRange(true);
      }
      if (!bars.length || isLoadingHistory || !hasMoreHistory) return;
      const rangeStart = event["xaxis.range[0]"];
      if (!rangeStart || typeof rangeStart !== "string") return;
      const leftMs = new Date(rangeStart).getTime();
      const firstMs = new Date(bars[0].ts).getTime();
      const lastMs = new Date(bars[bars.length - 1].ts).getTime();
      const span = Math.max(lastMs - firstMs, 1);
      const nearLeftEdge = leftMs <= firstMs + span * 0.1;
      if (!nearLeftEdge) return;
      const loaded = await loadOlderBars(1000);
      if (loaded === 0 && !hasMoreHistory) {
        setHistoryLimitReached(true);
      }
    },
    [bars, hasMoreHistory, isLoadingHistory, loadOlderBars]
  );

  // Quick Trade Handler
  const handleQuickTrade = useCallback(
    async (direction: "BUY" | "SELL") => {
      if (isTrading) return;
      setIsTrading(true);
      try {
        const size = 1;
        showToast(`Placing ${direction} order for ${size} ${panel.symbol}...`, "info");
        const res = await engineClient.placeOrder({
          symbol: panel.symbol,
          direction,
          size,
          type: "MARKET",
          reason: "quick_trade_chart"
        });
        if (res.order_id) {
          showToast(`Order Placed: ${direction} ${panel.symbol}`, "success");
        }
      } catch (err) {
        showToast(`Trade Failed: ${err instanceof Error ? err.message : String(err)}`, "error");
      } finally {
        setIsTrading(false);
      }
    },
    [panel.symbol, isTrading, showToast]
  );

  // Drawing completion handler
  const handleDrawingComplete = useCallback(
    (partial: Omit<Drawing, "id">) => {
      addDrawing({
        ...partial,
        symbol: panel.symbol,
        timeframe: panel.timeframe,
        color: partial.color || DEFAULT_DRAWING_COLOR,
      });
      setActiveTool("select");
    },
    [panel.symbol, panel.timeframe, addDrawing, setActiveTool]
  );

  // Chart context menu
  const handleChartContextMenu = useCallback(
    (e: React.MouseEvent) => {
      const items: ContextMenuItem[] = [
        {
          label: "Clear All Drawings",
          icon: "\u2717",
          action: clearDrawings,
          destructive: true,
        },
      ];
      showContextMenu(e, items);
    },
    [clearDrawings, showContextMenu]
  );

  // Is live data flowing?
  const isLive = quote !== null && Date.now() - new Date(quote.ts).getTime() < 15000;

  return (
    <div
      className={`chart-panel ${isFocused ? "focused" : ""}`}
      onMouseEnter={() => setIsFocused(true)}
      onMouseLeave={() => setIsFocused(false)}
      onClick={() => setIsFocused(true)}
    >
      {/* Panel Header */}
      <div className="panel-header">
        <div className="panel-header-left">
          {/* Symbol Selector */}
          <div className="panel-symbol-selector" ref={symbolDropdownRef}>
            <button
              className="panel-symbol-btn"
              onClick={() => {
                setShowSymbolDropdown(!showSymbolDropdown);
              }}
            >
              <span className="panel-symbol">{panel.symbol}</span>
              {quote && (
                <span className="panel-price">{quote.mid.toFixed(5)}</span>
              )}
              <span className="panel-symbol-caret">{showSymbolDropdown ? "\u25B2" : "\u25BC"}</span>
            </button>

            {showSymbolDropdown && (
              <div className="panel-symbol-dropdown">
                <input
                  type="text"
                  value={symbolSearch}
                  onChange={(e) => setSymbolSearch(e.target.value)}
                  placeholder="Search..."
                  className="panel-symbol-search"
                  autoFocus
                />
                <div className="panel-symbol-list">
                  {filteredSymbols.slice(0, 15).map((item) => (
                    <button
                      key={item.symbol}
                      className={`panel-symbol-item ${item.symbol === panel.symbol ? "active" : ""}`}
                      onClick={() => handleSymbolChange(item.symbol)}
                    >
                      <span>{item.symbol}</span>
                      <span className="item-name">{item.display_name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Timeframe Selector */}
          <div className="panel-timeframe-selector">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                className={`panel-tf-btn ${panel.timeframe === tf ? "active" : ""}`}
                onClick={() => handleTimeframeChange(tf)}
              >
                {tf}
              </button>
            ))}
          </div>

        </div>

        <div className="panel-header-right">
          <div className="panel-market-browser-wrapper" ref={marketBrowserRef}>
            <button
              className="panel-market-btn"
              onClick={() => setShowMarketBrowser((v) => !v)}
              title="Browse IG markets"
            >
              MKT
            </button>
            {showMarketBrowser && (
              <MarketBrowser
                items={catalogueItems}
                currentSymbol={panel.symbol}
                onSelectSymbol={(symbol) => {
                  handleSymbolChange(symbol);
                  setShowMarketBrowser(false);
                }}
              />
            )}
          </div>

          {/* 2E: Zoom Buttons */}
          <div className="panel-zoom-btns">
            {ZOOM_PRESETS.map((preset) => (
              <button
                key={preset.label}
                className={`zoom-btn ${activeZoom === preset.label ? "active" : ""}`}
                onClick={() => handleZoom(preset)}
              >
                {preset.label}
              </button>
            ))}
          </div>

          {/* 2H: Live/HIST Badge */}
          <span className={`live-badge ${isLive ? "live" : "hist"}`}>
            <span className={`live-dot ${isLive ? "dot-live" : "dot-hist"}`} />
            {isLive ? "LIVE" : "HIST"}
          </span>

          {/* Maximize button (multi-panel only) */}
          {canMaximize && onMaximize && (
            <button
              className="panel-maximize-btn"
              onClick={() => onMaximize(panel.id)}
              title="Maximize panel"
            >
              <svg width={14} height={14} viewBox="0 0 14 14">
                <rect x="1" y="1" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5" rx="1" />
              </svg>
            </button>
          )}

          {/* 2K: Overflow Menu */}
          <div className="panel-overflow-wrapper" ref={overflowRef}>
            <button
              className="panel-overflow-btn"
              onClick={() => setShowOverflowMenu(!showOverflowMenu)}
              title="More options"
            >
              {"\u22EF"}
            </button>

            {showOverflowMenu && (
              <div className="panel-overflow-menu">
                {/* Signals toggle */}
                <div style={{ position: "relative" }}>
                  <button
                    className={`overflow-item ${enabledBots.length > 0 ? "active" : ""}`}
                    onClick={() => {
                      setShowStrategyPopover(!showStrategyPopover);
                      setShowOverflowMenu(false);
                    }}
                  >
                    Signals{enabledBots.length > 0 ? ` (${enabledBots.length})` : ""}
                  </button>
                </div>

                {/* Indicators toggle */}
                <button
                  className={`overflow-item ${enabledIndicators.length > 0 ? "active" : ""}`}
                  onClick={() => {
                    setShowIndicatorPopover(!showIndicatorPopover);
                    setShowOverflowMenu(false);
                  }}
                >
                  Indicators ({enabledIndicators.length})
                </button>

                {/* Exec toggle */}
                <button
                  className={`overflow-item ${showExec ? "active" : ""}`}
                  onClick={() => {
                    toggleExecutions();
                    setShowOverflowMenu(false);
                  }}
                >
                  Executions {showExec ? "\u2713" : ""}
                </button>

                {/* SL/TP toggle */}
                <button
                  className={`overflow-item ${showSlTp ? "active" : ""}`}
                  onClick={() => {
                    toggleSlTp();
                    setShowOverflowMenu(false);
                  }}
                >
                  SL/TP {showSlTp ? "\u2713" : ""}
                </button>

                <div className="overflow-divider" />

                {/* Drawing tools toggle */}
                <button
                  className={`overflow-item ${showDrawingToolbar ? "active" : ""}`}
                  onClick={() => {
                    setShowDrawingToolbar(!showDrawingToolbar);
                    setShowOverflowMenu(false);
                  }}
                >
                  Drawing Tools {showDrawingToolbar ? "\u2713" : ""}
                </button>

                {/* Range slider toggle */}
                <button
                  className={`overflow-item ${showRangeSlider ? "active" : ""}`}
                  onClick={() => {
                    setShowRangeSlider(!showRangeSlider);
                    setShowOverflowMenu(false);
                  }}
                >
                  Range Slider {showRangeSlider ? "\u2713" : ""}
                </button>

                {/* Link group (multi-panel only) */}
                {!isOnlyPanel && (
                  <>
                    <div className="overflow-divider" />
                    <div className="overflow-link-group">
                      <span className="overflow-label">Link Group</span>
                      <div className="overflow-link-btns">
                        {LINK_GROUPS.map((lg) => (
                          <button
                            key={lg}
                            className={`panel-link-btn ${panel.linkGroup === lg ? "active" : ""}`}
                            onClick={() => {
                              handleLinkGroupChange(lg);
                              setShowOverflowMenu(false);
                            }}
                          >
                            {lg === "none" ? "\u25CB" : lg}
                          </button>
                        ))}
                      </div>
                    </div>
                  </>
                )}

                <div className="overflow-divider" />

                {/* Clear drawings */}
                <button
                  className="overflow-item overflow-danger"
                  onClick={() => {
                    clearDrawings();
                    setShowOverflowMenu(false);
                  }}
                >
                  Clear Drawings
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Drawing Toolbar (inline below header, activated from overflow menu) */}
      {showDrawingToolbar && (
        <div className="panel-drawing-bar">
          <DrawingToolbar
            activeTool={activeTool}
            onToolChange={setActiveTool}
          />
          {activeTool !== "select" && (
            <span className="drawing-active-label">
              Drawing: {activeTool}
            </span>
          )}
        </div>
      )}

      {/* Popovers (rendered outside overflow to position correctly) */}
      {showStrategyPopover && (
        <div className="panel-popover-anchor">
          <StrategyPopover
            bots={panel.bots}
            onUpdate={handleBotsUpdate}
            onClose={() => setShowStrategyPopover(false)}
          />
        </div>
      )}
      {showIndicatorPopover && (
        <div className="panel-popover-anchor">
          <IndicatorPopover
            indicators={panel.indicators}
            onUpdate={handleIndicatorsUpdate}
            onClose={() => setShowIndicatorPopover(false)}
          />
        </div>
      )}

      {/* Chart Area */}
      <div className="panel-chart">
        {barsLoading ? (
          <div className="panel-loading">
            <div className="panel-loading-inner">
              <div className="panel-loading-spinner" />
              <span>Loading {panel.symbol} {panel.timeframe}...</span>
            </div>
          </div>
        ) : bars.length === 0 ? (
          <div className="panel-empty">
            <div className="panel-empty-inner">
              <span className="panel-empty-icon">&#x1F4CA;</span>
              <p>No data for {panel.symbol} {panel.timeframe}</p>
              <p className="panel-empty-hint">Run Quick Sync from the Library tab to fetch historical bars.</p>
            </div>
          </div>
        ) : (
          <>
            <CandleChart
              bars={bars}
              overlays={overlays}
              signals={panel.showMarkers ? signals : []}
              executions={showExec ? executions : []}
              slTpLevels={showSlTp ? slTpLevels : []}
              drawings={chartDrawings}
              activeTool={activeTool}
              onDrawingComplete={handleDrawingComplete}
              onContextMenu={handleChartContextMenu}
              onRelayout={handleRelayout}
              height={undefined}
              symbol={panel.symbol}
              timeframe={panel.timeframe}
              xRange={effectiveXRange}
              showRangeSlider={showRangeSlider}
            />
            {/* Quick Trade Overlay */}
            <div className="chart-trade-overlay">
              <button
                className="trade-btn sell"
                onClick={() => handleQuickTrade("SELL")}
                disabled={isTrading}
              >
                SELL
              </button>
              <button
                className="trade-btn buy"
                onClick={() => handleQuickTrade("BUY")}
                disabled={isTrading}
              >
                BUY
              </button>
            </div>
          </>
        )}
      </div>

      {/* Panel Status */}
      <div className="panel-status">
        <span className="panel-status-bars">{bars.length} bars</span>
        {isLoadingHistory && <span className="panel-status-range">loading more history...</span>}
        {historyLimitReached && (
          <span className="panel-status-range">history limit reached</span>
        )}
        {barsStart && barsEnd && (
          <span className="panel-status-range">
            {new Date(barsStart).toLocaleDateString()} - {new Date(barsEnd).toLocaleDateString()}
          </span>
        )}
        {requestedLimit != null && requestedLimit > 0 && (
          <span className="panel-status-range">
            cov {bars.length}/{requestedLimit}
            {coveragePct != null ? ` (${coveragePct.toFixed(1)}%)` : ""}
            {source ? ` ${source}` : ""}
          </span>
        )}
        {(coveragePct ?? 100) < 70 && (
          <span className="panel-status-range">
            IG history limited for {panel.symbol} {panel.timeframe} (try 1h/4h or another crypto in MKT)
          </span>
        )}
        {quote && (
          <>
            <span className="panel-status-bid">B: {quote.bid.toFixed(5)}</span>
            <span className="panel-status-ask">A: {quote.ask.toFixed(5)}</span>
          </>
        )}
        <span className="panel-status-time">
          {bars.length > 0 && new Date(bars[bars.length - 1].ts).toLocaleTimeString()}
        </span>
      </div>

      {/* Context Menu */}
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menu.items}
          onClose={closeContextMenu}
        />
      )}
    </div>
  );
}
