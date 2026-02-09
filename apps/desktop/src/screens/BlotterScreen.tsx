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
import {
  engineClient,
  ExecutionEvent,
  ExecutionFill,
  ExecutionOrder,
} from "../lib/engineClient";

// =============================================================================
// Types
// =============================================================================

type BlotterTab = "events" | "fills" | "orders";

// =============================================================================
// Component
// =============================================================================

export function BlotterScreen() {
  const [activeTab, setActiveTab] = useState<BlotterTab>("fills");
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [fills, setFills] = useState<ExecutionFill[]>([]);
  const [orders, setOrders] = useState<ExecutionOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [symbolFilter, setSymbolFilter] = useState("");
  const [directionFilter, setDirectionFilter] = useState<"" | "BUY" | "SELL">("");

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

  // Filter helpers
  const filterBySymbolAndDirection = useCallback(
    <T extends { symbol: string; direction?: string }>(items: T[]): T[] => {
      return items.filter((item) => {
        if (symbolFilter && !item.symbol.toLowerCase().includes(symbolFilter.toLowerCase())) {
          return false;
        }
        if (directionFilter && item.direction !== directionFilter) {
          return false;
        }
        return true;
      });
    },
    [symbolFilter, directionFilter]
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

    navigator.clipboard.writeText(csv).catch(console.error);
  }, [activeTab, filteredEvents, filteredFills, filteredOrders]);

  return (
    <div className="blotter-screen">
      <div className="blotter-header">
        <h2>Trade Blotter</h2>
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
      </div>

      {/* Content */}
      <div className="blotter-content">
        {isLoading ? (
          <div className="blotter-loading">Loading...</div>
        ) : error ? (
          <div className="blotter-error">
            <p>{error}</p>
            <button onClick={fetchData}>Retry</button>
          </div>
        ) : activeTab === "events" ? (
          <EventsTable events={filteredEvents} />
        ) : activeTab === "fills" ? (
          <FillsTable fills={filteredFills} />
        ) : (
          <OrdersTable orders={filteredOrders} />
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

function EventsTable({ events }: { events: ExecutionEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="blotter-empty">
        <p>No execution events</p>
        <span className="hint">Events appear when the execution engine processes signals</span>
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
          </tr>
        </thead>
        <tbody>
          {events.map((event, idx) => (
            <tr key={idx}>
              <td className="mono">{formatTimestamp(event.ts)}</td>
              <td>
                <span className={`event-type-badge type-${event.type.toLowerCase()}`}>
                  {event.type}
                </span>
              </td>
              <td className="mono">{event.symbol}</td>
              <td className={event.direction === "BUY" ? "positive" : event.direction === "SELL" ? "negative" : ""}>
                {event.direction ?? "—"}
              </td>
              <td>{event.bot ?? "—"}</td>
              <td className="mono">{event.price?.toFixed(5) ?? "—"}</td>
              <td className="mono">{event.size ?? "—"}</td>
              <td className="reason-col">{event.reason ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FillsTable({ fills }: { fills: ExecutionFill[] }) {
  if (fills.length === 0) {
    return (
      <div className="blotter-empty">
        <p>No fills</p>
        <span className="hint">Fills appear when orders are executed by the broker</span>
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
          </tr>
        </thead>
        <tbody>
          {fills.map((fill, idx) => (
            <tr key={idx}>
              <td className="mono">{formatTimestamp(fill.ts)}</td>
              <td className="mono">{fill.symbol}</td>
              <td className={fill.direction === "BUY" ? "positive" : "negative"}>
                {fill.direction}
              </td>
              <td className="mono">{fill.price.toFixed(5)}</td>
              <td className="mono">{fill.size}</td>
              <td>{fill.bot ?? "—"}</td>
              <td className={`mono ${(fill.pnl ?? 0) >= 0 ? "positive" : "negative"}`}>
                {fill.pnl !== undefined ? fill.pnl.toFixed(2) : "—"}
              </td>
              <td>{fill.is_close ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OrdersTable({ orders }: { orders: ExecutionOrder[] }) {
  if (orders.length === 0) {
    return (
      <div className="blotter-empty">
        <p>No orders</p>
        <span className="hint">Orders appear when the execution engine routes trading signals</span>
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
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.order_id}>
              <td className="mono">{formatTimestamp(order.ts)}</td>
              <td className="mono">{order.order_id.slice(0, 12)}</td>
              <td className="mono">{order.symbol}</td>
              <td className={order.direction === "BUY" ? "positive" : "negative"}>
                {order.direction}
              </td>
              <td className="mono">{order.size}</td>
              <td>
                <span className={`order-status-badge status-${order.status.toLowerCase()}`}>
                  {order.status}
                </span>
              </td>
              <td className="mono">{order.entry_price?.toFixed(5) ?? "—"}</td>
              <td className="mono">{order.sl_price?.toFixed(5) ?? "—"}</td>
              <td className="mono">{order.tp_price?.toFixed(5) ?? "—"}</td>
              <td className="mono">{order.fill_price?.toFixed(5) ?? "—"}</td>
              <td>{order.bot ?? "—"}</td>
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
