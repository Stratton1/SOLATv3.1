/**
 * ChartPanel - individual chart panel within workspace grid.
 *
 * Contains:
 * - Panel header with symbol/timeframe selectors
 * - CandleChart component with markers, SL/TP, executions
 * - Status line
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { CandleChart } from "../CandleChart";
import { DrawingToolbar } from "../DrawingToolbar";
import { ContextMenu, useContextMenu, type ContextMenuItem } from "../ContextMenu";
import { StrategyPopover } from "./StrategyPopover";
import { IndicatorPopover } from "./IndicatorPopover";
import { useBars } from "../../hooks/useBars";
import { useOverlays } from "../../hooks/useOverlays";
import { useSignals } from "../../hooks/useSignals";
import { useCatalogue } from "../../hooks/useCatalogue";
import { useMarketStatus } from "../../hooks/useMarketStatus";
import { useMarketSubscription } from "../../hooks/useMarketSubscription";
import { useWorkspace } from "../../hooks/useWorkspace";
import { useWsEvents, QuoteUpdateEvent, BarUpdateEvent } from "../../hooks/useWsEvents";
import { useExecutionEvents } from "../../hooks/useExecutionEvents";
import { useDrawings } from "../../hooks/useDrawings";
import { Panel, PanelBot, PanelIndicator, TIMEFRAMES, LinkGroup } from "../../lib/workspace";
import { Drawing, DEFAULT_DRAWING_COLOR } from "../../lib/drawings";

// =============================================================================
// Types
// =============================================================================

interface ChartPanelProps {
  panel: Panel;
  index: number;
  isOnlyPanel?: boolean;
}

const LINK_GROUPS: LinkGroup[] = ["none", "A", "B", "C"];

// =============================================================================
// Component
// =============================================================================

export function ChartPanel({ panel, index: _index, isOnlyPanel = false }: ChartPanelProps) {
  const { updatePanel, setLinkedTimeframe, setLinkedSymbol } = useWorkspace();
  const { items: catalogueItems } = useCatalogue();
  const { status: marketStatus } = useMarketStatus();
  const { subscribe } = useMarketSubscription();

  // Local state
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [quote, setQuote] = useState<QuoteUpdateEvent | null>(null);
  const [showStrategyPopover, setShowStrategyPopover] = useState(false);
  const [showIndicatorPopover, setShowIndicatorPopover] = useState(false);

  // Data hooks
  const {
    bars,
    isLoading: barsLoading,
    start: barsStart,
    end: barsEnd,
    appendBar,
  } = useBars({
    symbol: panel.symbol,
    timeframe: panel.timeframe,
    limit: panel.lookbackBars,
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

  // Subscribe to symbol on mount
  useEffect(() => {
    const item = catalogueItems.find((i) => i.symbol === panel.symbol);
    if (item && marketStatus && !marketStatus.subscriptions.includes(panel.symbol)) {
      subscribe([panel.symbol], "stream").catch(console.error);
    }
  }, [panel.symbol, catalogueItems, marketStatus, subscribe]);

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
      updatePanel(panel.id, { symbol });
      if (panel.linkGroup !== "none") {
        setLinkedSymbol(panel.linkGroup, symbol);
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

  // Drawing completion handler
  const handleDrawingComplete = useCallback(
    (partial: Omit<Drawing, "id">) => {
      addDrawing({
        ...partial,
        symbol: panel.symbol,
        timeframe: panel.timeframe,
        color: partial.color || DEFAULT_DRAWING_COLOR,
      });
      // Reset to select after drawing
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
          <div className="panel-symbol-selector">
            <button
              className="panel-symbol-btn"
              onClick={() => setShowSymbolDropdown(!showSymbolDropdown)}
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
          {/* Drawing Tools (show when focused) */}
          {isFocused && (
            <DrawingToolbar
              activeTool={activeTool}
              onToolChange={setActiveTool}
            />
          )}

          {/* Overlay Toggles */}
          <div className="panel-overlay-toggles">
            <div style={{ position: "relative" }}>
              <button
                className={`panel-toggle-btn ${enabledBots.length > 0 ? "active" : ""}`}
                onClick={() => setShowStrategyPopover(!showStrategyPopover)}
                title="Select strategies for signals"
              >
                Signals{enabledBots.length > 0 ? ` (${enabledBots.length})` : ""}
              </button>
              {showStrategyPopover && (
                <StrategyPopover
                  bots={panel.bots}
                  onUpdate={handleBotsUpdate}
                  onClose={() => setShowStrategyPopover(false)}
                />
              )}
            </div>
            <div style={{ position: "relative" }}>
              <button
                className={`panel-toggle-btn ${enabledIndicators.length > 0 ? "active" : ""}`}
                onClick={() => setShowIndicatorPopover(!showIndicatorPopover)}
                title="Manage indicators"
              >
                Ind ({enabledIndicators.length})
              </button>
              {showIndicatorPopover && (
                <IndicatorPopover
                  indicators={panel.indicators}
                  onUpdate={handleIndicatorsUpdate}
                  onClose={() => setShowIndicatorPopover(false)}
                />
              )}
            </div>
            <button
              className={`panel-toggle-btn ${showExec ? "active" : ""}`}
              onClick={toggleExecutions}
              title="Execution markers"
            >
              Exec
            </button>
            <button
              className={`panel-toggle-btn ${showSlTp ? "active" : ""}`}
              onClick={toggleSlTp}
              title="SL/TP levels"
            >
              SL/TP
            </button>
          </div>

          {/* Link Group (only useful in multi-panel layouts) */}
          {!isOnlyPanel && (
            <div className="panel-link-selector">
              {LINK_GROUPS.map((lg) => (
                <button
                  key={lg}
                  className={`panel-link-btn ${panel.linkGroup === lg ? "active" : ""}`}
                  onClick={() => handleLinkGroupChange(lg)}
                  title={lg === "none" ? "Unlinked" : `Link Group ${lg}`}
                >
                  {lg === "none" ? "\u25CB" : lg}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

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
            height={undefined}
          />
        )}
      </div>

      {/* Panel Status */}
      <div className="panel-status">
        <span className="panel-status-bars">{bars.length} bars</span>
        {barsStart && barsEnd && (
          <span className="panel-status-range">
            {new Date(barsStart).toLocaleDateString()} - {new Date(barsEnd).toLocaleDateString()}
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

      {/* Close dropdown on outside click */}
      {showSymbolDropdown && (
        <div
          className="dropdown-backdrop"
          onClick={() => setShowSymbolDropdown(false)}
        />
      )}

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
