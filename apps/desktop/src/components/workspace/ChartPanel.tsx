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
import { useBars } from "../../hooks/useBars";
import { useOverlays } from "../../hooks/useOverlays";
import { useSignals } from "../../hooks/useSignals";
import { useCatalogue } from "../../hooks/useCatalogue";
import { useMarketStatus } from "../../hooks/useMarketStatus";
import { useMarketSubscription } from "../../hooks/useMarketSubscription";
import { useWorkspace } from "../../hooks/useWorkspace";
import { useWsEvents, QuoteUpdateEvent, BarUpdateEvent } from "../../hooks/useWsEvents";
import { useAvailability } from "../../hooks/useAvailability";
import { useExecutionEvents } from "../../hooks/useExecutionEvents";
import { Panel, TIMEFRAMES, LinkGroup } from "../../lib/workspace";

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
  const { enrichedItems } = useCatalogue();
  const { status: marketStatus } = useMarketStatus();
  const { subscribe } = useMarketSubscription();

  // Local state
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [quote, setQuote] = useState<QuoteUpdateEvent | null>(null);

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
    bars: shouldFetchOverlays ? bars : undefined,
  });

  const { signals } = useSignals({
    symbol: panel.symbol,
    timeframe: panel.timeframe,
  });

  // Execution markers + SL/TP levels
  const showExec = panel.showExecutions !== false;
  const showSlTp = panel.showSlTp !== false;
  const { executions, slTpLevels } = useExecutionEvents({
    symbol: panel.symbol,
    enabled: showExec || showSlTp,
  });

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
    const item = enrichedItems.find((i) => i.symbol === panel.symbol);
    if (item && marketStatus && !marketStatus.subscriptions.includes(panel.symbol)) {
      subscribe([panel.symbol], "stream").catch(console.error);
    }
  }, [panel.symbol, enrichedItems, marketStatus, subscribe]);

  // Filter symbols for search
  const filteredSymbols = useMemo(() => {
    const query = symbolSearch.toLowerCase();
    return enrichedItems.filter(
      (item) =>
        item.symbol.toLowerCase().includes(query) ||
        item.display_name.toLowerCase().includes(query)
    );
  }, [enrichedItems, symbolSearch]);

  const { isTimeframeAvailable } = useAvailability();

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

  const toggleMarkers = useCallback(() => {
    updatePanel(panel.id, { showMarkers: !panel.showMarkers });
  }, [panel.id, panel.showMarkers, updatePanel]);

  const toggleSlTp = useCallback(() => {
    updatePanel(panel.id, { showSlTp: !(panel.showSlTp !== false) });
  }, [panel.id, panel.showSlTp, updatePanel]);

  const toggleExecutions = useCallback(() => {
    updatePanel(panel.id, { showExecutions: !(panel.showExecutions !== false) });
  }, [panel.id, panel.showExecutions, updatePanel]);

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
                className={`panel-tf-btn ${panel.timeframe === tf ? "active" : ""} ${!isTimeframeAvailable(panel.symbol, tf) ? "dimmed" : ""}`}
                onClick={() => handleTimeframeChange(tf)}
                title={!isTimeframeAvailable(panel.symbol, tf) ? "No data available" : undefined}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div className="panel-header-right">
          {/* Link Group */}
          <div className="panel-link-selector">
            {LINK_GROUPS.map((lg) => (
              <button
                key={lg}
                className={`panel-link-btn ${panel.linkGroup === lg ? "active" : ""}`}
                onClick={() => handleLinkGroupChange(lg)}
                title={lg === "none" ? "Unlinked" : `Link Group ${lg}`}
              >
                {lg === "none" ? "○" : lg}
              </button>
            ))}
          </div>

          {/* Markers Toggle */}
          <button
            className={`panel-markers-btn ${panel.showMarkers ? "active" : ""}`}
            onClick={toggleMarkers}
            title="Toggle signal markers"
          >
            ◆
          </button>

          {/* Executions Toggle */}
          <button
            className={`panel-markers-btn ${showExec ? "active" : ""}`}
            onClick={toggleExecutions}
            title="Toggle execution markers"
          >
            ⬥
          </button>

          {/* SL/TP Toggle */}
          <button
            className={`panel-markers-btn ${showSlTp ? "active" : ""}`}
            onClick={toggleSlTp}
            title="Toggle SL/TP lines"
          >
            ═
          </button>
        </div>
      </div>

      {/* Chart Area */}
      <div className="panel-chart">
        {barsLoading ? (
          <div className="panel-loading">Loading...</div>
        ) : bars.length === 0 ? (
          <div className="panel-empty">
            <p>No data for {panel.symbol} {panel.timeframe}</p>
          </div>
        ) : (
          <CandleChart
            bars={bars}
            overlays={overlays}
            signals={panel.showMarkers ? signals : []}
            executions={showExec ? executions : []}
            slTpLevels={showSlTp ? slTpLevels : []}
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
    </div>
  );
}
