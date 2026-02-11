/**
 * Trade blotter screen - shows execution events, fills, and orders.
 *
 * Features:
 * - Tabbed view: Events | Fills | Orders
 * - Symbol/direction filters
 * - CSV export via clipboard
 * - Auto-refresh
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  engineClient,
  ExecutionEvent,
  ExecutionFill,
  ExecutionOrder,
} from "../lib/engineClient";
import { InfoTip } from "../components/InfoTip";
import { useToast } from "../context/ToastContext";

// =============================================================================
// Types
// =============================================================================

type BlotterTab = "events" | "fills" | "orders";

// =============================================================================
// Component
// =============================================================================

export function BlotterScreen() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [activeTab, setActiveTab] = useState<BlotterTab>("fills");
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [fills, setFills] = useState<ExecutionFill[]>([]);
  const [orders, setOrders] = useState<ExecutionOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [symbolFilter, setSymbolFilter] = useState("");
  const [directionFilter, setDirectionFilter] = useState<"" | "BUY" | "SELL">("");
  const [botFilter, setBotFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [eventsRes, fillsRes, ordersRes] = await Promise.all([
        engineClient.getExecutionEvents({ limit: 500 }).catch(() => null),
        engineClient.getExecutionFills({ limit: 500 }).catch(() => null),
        engineClient.getExecutionOrders({ limit: 500 }).catch(() => null),
      ]);

      if (eventsRes) setEvents(eventsRes.events);
      if (fillsRes) setFills(fillsRes.fills);
      if (ordersRes) setOrders(ordersRes.orders);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load blotter data");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 15s
  useEffect(() => {
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Unique bot names for filter dropdown
  const uniqueBots = useMemo(() => {
    const bots = new Set<string>();
    events.forEach((e) => e.bot && bots.add(e.bot));
    fills.forEach((f) => f.bot && bots.add(f.bot));
    orders.forEach((o) => o.bot && bots.add(o.bot));
    return Array.from(bots).sort();
  }, [events, fills, orders]);

  const hasFilters = symbolFilter || directionFilter || botFilter || dateFrom || dateTo;

  const clearFilters = useCallback(() => {
    setSymbolFilter("");
    setDirectionFilter("");
    setBotFilter("");
    setDateFrom("");
    setDateTo("");
  }, []);

  // Filter helpers
  const filterBySymbolAndDirection = useCallback(
    <T extends { ts: string; symbol: string; direction?: string; bot?: string }>(items: T[]): T[] => {
      return items.filter((item) => {
        if (symbolFilter && !item.symbol.toLowerCase().includes(symbolFilter.toLowerCase())) {
          return false;
        }
        if (directionFilter && item.direction !== directionFilter) {
          return false;
        }
        if (botFilter && item.bot !== botFilter) {
          return false;
        }
        if (dateFrom && item.ts < dateFrom) {
          return false;
        }
        if (dateTo && item.ts > dateTo + "T23:59:59") {
          return false;
        }
        return true;
      });
    },
    [symbolFilter, directionFilter, botFilter, dateFrom, dateTo]
  );

  const filteredEvents = useMemo(
    () => filterBySymbolAndDirection(events),
    [events, filterBySymbolAndDirection]
  );

  const filteredFills = useMemo(
    () => filterBySymbolAndDirection(fills),
    [fills, filterBySymbolAndDirection]
  );

  const filteredOrders = useMemo(
    () => filterBySymbolAndDirection(orders),
    [orders, filterBySymbolAndDirection]
  );

  // CSV Export
  const exportCsv = useCallback(() => {
    let csv = "";
    if (activeTab === "events") {
      csv = "Timestamp,Type,Symbol,Direction,Bot,Price,Size,Reason\n";
      filteredEvents.forEach((e) => {
        csv += `${e.ts},${e.type},${e.symbol},${e.direction ?? ""},${e.bot ?? ""},${e.price ?? ""},${e.size ?? ""},${e.reason ?? ""}\n`;
      });
    } else if (activeTab === "fills") {
      csv = "Timestamp,Symbol,Direction,Price,Size,OrderID,Bot,PnL,IsClose\n";
      filteredFills.forEach((f) => {
        csv += `${f.ts},${f.symbol},${f.direction},${f.price},${f.size},${f.order_id},${f.bot ?? ""},${f.pnl ?? ""},${f.is_close ?? ""}\n`;
      });
    } else {
      csv = "OrderID,Timestamp,Symbol,Direction,Size,Status,EntryPrice,SL,TP,Bot,FillPrice\n";
      filteredOrders.forEach((o) => {
        csv += `${o.order_id},${o.ts},${o.symbol},${o.direction},${o.size},${o.status},${o.entry_price ?? ""},${o.sl_price ?? ""},${o.tp_price ?? ""},${o.bot ?? ""},${o.fill_price ?? ""}\n`;
      });
    }

    const rowCount =
      activeTab === "events"
        ? filteredEvents.length
        : activeTab === "fills"
          ? filteredFills.length
          : filteredOrders.length;

    navigator.clipboard
      .writeText(csv)
      .then(() => {
        showToast(`Copied ${rowCount} ${activeTab} rows to clipboard`, "success");
      })
      .catch(() => {
        showToast("Failed to copy to clipboard", "error");
      });
  }, [activeTab, filteredEvents, filteredFills, filteredOrders, showToast]);

  // Deep link: navigate to Terminal and scroll chart to timestamp
  const viewOnChart = useCallback(
    (symbol: string, ts: string) => {
      sessionStorage.setItem(
        "solat_chart_deeplink",
        JSON.stringify({ symbol, timeframe: "1h", timestamp: ts })
      );
      navigate("/terminal");
    },
    [navigate]
  );

  return (
    <div className="blotter-screen">
      <div className="blotter-header">
        <h2>
          Trade Blotter
          <InfoTip text="The blotter shows all execution activity: events (signal processing), fills (broker confirmations), and orders (routed trades). Data refreshes automatically every 15 seconds. Use 'Copy CSV' to export the current filtered view to your clipboard." />
        </h2>
        <div className="blotter-actions">
          <button className="blotter-export-btn" onClick={exportCsv}>
            Copy CSV
          </button>
          <button className="refresh-btn" onClick={fetchData}>
            Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="blotter-tabs">
        <button
          className={`blotter-tab ${activeTab === "events" ? "active" : ""}`}
          onClick={() => setActiveTab("events")}
        >
          Events ({events.length})
        </button>
        <button
          className={`blotter-tab ${activeTab === "fills" ? "active" : ""}`}
          onClick={() => setActiveTab("fills")}
        >
          Fills ({fills.length})
        </button>
        <button
          className={`blotter-tab ${activeTab === "orders" ? "active" : ""}`}
          onClick={() => setActiveTab("orders")}
        >
          Orders ({orders.length})
        </button>
      </div>

      {/* Filters */}
      <div className="blotter-filters">
        <input
          type="text"
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          placeholder="Filter by symbol..."
          className="blotter-filter-input"
        />
        <select
          value={directionFilter}
          onChange={(e) => setDirectionFilter(e.target.value as "" | "BUY" | "SELL")}
          className="blotter-filter-select"
        >
          <option value="">All directions</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
        <select
          value={botFilter}
          onChange={(e) => setBotFilter(e.target.value)}
          className="blotter-filter-select"
        >
          <option value="">All bots</option>
          {uniqueBots.map((bot) => (
            <option key={bot} value={bot}>{bot}</option>
          ))}
        </select>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="blotter-date-input"
          title="From date"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="blotter-date-input"
          title="To date"
        />
        {hasFilters && (
          <button className="blotter-clear-filters-btn" onClick={clearFilters}>
            Clear Filters
          </button>
        )}
      </div>

      {/* Content */}
      <div className="blotter-content">
        {isLoading ? (
          <div className="blotter-loading">
            <div className="skeleton skeleton-row" />
            <div className="skeleton skeleton-row" />
            <div className="skeleton skeleton-row" />
            <div className="skeleton skeleton-row" />
          </div>
        ) : error ? (
          <div className="blotter-error">
            <p>{error}</p>
            <button onClick={fetchData}>Retry</button>
          </div>
        ) : activeTab === "events" ? (
          <EventsTable events={filteredEvents} onViewChart={viewOnChart} />
        ) : activeTab === "fills" ? (
          <FillsTable fills={filteredFills} onViewChart={viewOnChart} />
        ) : (
          <OrdersTable orders={filteredOrders} onViewChart={viewOnChart} />
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

function EventsTable({ events, onViewChart }: { events: ExecutionEvent[]; onViewChart: (symbol: string, ts: string) => void }) {
  if (events.length === 0) {
    return (
      <div className="blotter-empty">
        <p className="blotter-empty-title">No execution events yet</p>
        <p className="blotter-empty-hint">
          Events are logged when the execution engine processes strategy signals.
          Arm the engine and subscribe to market data to start generating events.
        </p>
        <p className="blotter-empty-hint">
          Tip: Enable Autopilot on the Status page to automatically run your
          allowlisted strategies on incoming bar data (DEMO only).
        </p>
      </div>
    );
  }

  return (
    <div className="blotter-table-wrapper">
      <table className="blotter-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Type</th>
            <th>Symbol</th>
            <th>Direction</th>
            <th>Bot</th>
            <th>Price</th>
            <th>Size</th>
            <th>Reason</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {events.map((event, idx) => (
            <tr key={idx}>
              <td className="mono num">{formatTimestamp(event.ts)}</td>
              <td>
                <span className={`event-type-badge type-${event.type.toLowerCase()}`}>
                  {event.type}
                </span>
              </td>
              <td className="mono">{event.symbol}</td>
              <td className={event.direction === "BUY" ? "positive" : event.direction === "SELL" ? "negative" : ""}>
                {event.direction ?? "\u2014"}
              </td>
              <td>{event.bot ?? "\u2014"}</td>
              <td className="mono num">{event.price?.toFixed(5) ?? "\u2014"}</td>
              <td className="mono num">{event.size ?? "\u2014"}</td>
              <td className="reason-col">{event.reason ?? "\u2014"}</td>
              <td>
                <button
                  className="blotter-view-btn"
                  onClick={() => onViewChart(event.symbol, event.ts)}
                  title="View on Chart"
                >
                  {"\u25C9"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FillsTable({ fills, onViewChart }: { fills: ExecutionFill[]; onViewChart: (symbol: string, ts: string) => void }) {
  if (fills.length === 0) {
    return (
      <div className="blotter-empty">
        <p className="blotter-empty-title">No fills yet</p>
        <p className="blotter-empty-hint">
          Fills appear when the broker confirms order execution. In DEMO mode,
          the fill simulator generates synthetic fills. In LIVE mode, fills come
          from IG Markets.
        </p>
        <p className="blotter-empty-hint">
          Tip: Use Autopilot to generate fills automatically from your
          recommended strategy combos.
        </p>
      </div>
    );
  }

  return (
    <div className="blotter-table-wrapper">
      <table className="blotter-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Symbol</th>
            <th>Direction</th>
            <th>Price</th>
            <th>Size</th>
            <th>Bot</th>
            <th>PnL</th>
            <th>Close?</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {fills.map((fill, idx) => (
            <tr key={idx}>
              <td className="mono num">{formatTimestamp(fill.ts)}</td>
              <td className="mono">{fill.symbol}</td>
              <td className={fill.direction === "BUY" ? "positive" : "negative"}>
                {fill.direction}
              </td>
              <td className="mono num">{fill.price.toFixed(5)}</td>
              <td className="mono num">{fill.size}</td>
              <td>{fill.bot ?? "\u2014"}</td>
              <td className={`mono num ${(fill.pnl ?? 0) >= 0 ? "positive" : "negative"}`}>
                {fill.pnl !== undefined ? fill.pnl.toFixed(2) : "\u2014"}
              </td>
              <td>{fill.is_close ? "Yes" : "No"}</td>
              <td>
                <button
                  className="blotter-view-btn"
                  onClick={() => onViewChart(fill.symbol, fill.ts)}
                  title="View on Chart"
                >
                  {"\u25C9"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OrdersTable({ orders, onViewChart }: { orders: ExecutionOrder[]; onViewChart: (symbol: string, ts: string) => void }) {
  if (orders.length === 0) {
    return (
      <div className="blotter-empty">
        <p className="blotter-empty-title">No orders yet</p>
        <p className="blotter-empty-hint">
          Orders are created when strategy signals pass through the risk engine
          and are routed for execution. Each order tracks its lifecycle from
          creation through fill or rejection.
        </p>
        <p className="blotter-empty-hint">
          Tip: Run a walk-forward optimisation, apply the recommended set to
          your allowlist, then enable Autopilot to start generating orders.
        </p>
      </div>
    );
  }

  return (
    <div className="blotter-table-wrapper">
      <table className="blotter-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Order ID</th>
            <th>Symbol</th>
            <th>Direction</th>
            <th>Size</th>
            <th>Status</th>
            <th>Entry</th>
            <th>SL</th>
            <th>TP</th>
            <th>Fill Price</th>
            <th>Bot</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.order_id}>
              <td className="mono num">{formatTimestamp(order.ts)}</td>
              <td className="mono">{order.order_id.slice(0, 12)}</td>
              <td className="mono">{order.symbol}</td>
              <td className={order.direction === "BUY" ? "positive" : "negative"}>
                {order.direction}
              </td>
              <td className="mono num">{order.size}</td>
              <td>
                <span className={`order-status-badge status-${order.status.toLowerCase()}`}>
                  {order.status}
                </span>
              </td>
              <td className="mono num">{order.entry_price?.toFixed(5) ?? "\u2014"}</td>
              <td className="mono num">{order.sl_price?.toFixed(5) ?? "\u2014"}</td>
              <td className="mono num">{order.tp_price?.toFixed(5) ?? "\u2014"}</td>
              <td className="mono num">{order.fill_price?.toFixed(5) ?? "\u2014"}</td>
              <td>{order.bot ?? "\u2014"}</td>
              <td>
                <button
                  className="blotter-view-btn"
                  onClick={() => onViewChart(order.symbol, order.ts)}
                  title="View on Chart"
                >
                  {"\u25C9"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// =============================================================================
// Helpers
// =============================================================================

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
}
