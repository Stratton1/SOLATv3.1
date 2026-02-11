/**
 * Hook for handling WebSocket events with typed handlers.
 */

import { useEffect, useRef } from "react";
import { Bar } from "../lib/engineClient";

const DEBUG_INGEST_URL = "http://127.0.0.1:7245/ingest/b34e6a51-242b-4280-9e50-b775760b6116";

// WebSocket event types from engine
export interface QuoteUpdateEvent {
  type: "quote_update";
  symbol: string;
  bid: number;
  ask: number;
  mid: number;
  ts: string;
}

export interface BarUpdateEvent {
  type: "bar_update";
  symbol: string;
  timeframe: string;
  bar: Bar;
  source: string;
}

export interface MarketStatusEvent {
  type: "market_status";
  connected: boolean;
  stale: boolean;
  mode: string;
  last_tick_ts: string | null;
  subscriptions: string[];
}

export interface ExecutionEvent {
  type: "execution_event";
  event_type: string;
  data: Record<string, unknown>;
}

export interface HeartbeatEvent {
  type: "heartbeat";
  timestamp: string;
  uptime_seconds: number;
}

export type WsEvent =
  | QuoteUpdateEvent
  | BarUpdateEvent
  | MarketStatusEvent
  | ExecutionEvent
  | HeartbeatEvent;

interface UseWsEventsOptions {
  wsUrl?: string;
  onQuote?: (event: QuoteUpdateEvent) => void;
  onBar?: (event: BarUpdateEvent) => void;
  onMarketStatus?: (event: MarketStatusEvent) => void;
  onExecution?: (event: ExecutionEvent) => void;
  onHeartbeat?: (event: HeartbeatEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

export function useWsEvents({
  wsUrl = "ws://127.0.0.1:8765/ws",
  onQuote,
  onBar,
  onMarketStatus,
  onExecution,
  onHeartbeat,
  onConnect,
  onDisconnect,
}: UseWsEventsOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlersRef = useRef({
    onQuote,
    onBar,
    onMarketStatus,
    onExecution,
    onHeartbeat,
    onConnect,
    onDisconnect,
  });

  useEffect(() => {
    handlersRef.current = {
      onQuote,
      onBar,
      onMarketStatus,
      onExecution,
      onHeartbeat,
      onConnect,
      onDisconnect,
    };
  }, [onQuote, onBar, onMarketStatus, onExecution, onHeartbeat, onConnect, onDisconnect]);

  useEffect(() => {
    let mounted = true;

    const connect = () => {
      if (!mounted) return;

      // #region agent log H5 ws connect attempt
      fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H5", location: "useWsEvents.ts:connect:start", message: "WebSocket connect attempt", data: { wsUrl }, timestamp: Date.now() }) }).catch(() => {});
      // #endregion
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // #region agent log H5 ws open
        fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H5", location: "useWsEvents.ts:onopen", message: "WebSocket connected", data: { wsUrl, readyState: ws.readyState }, timestamp: Date.now() }) }).catch(() => {});
        // #endregion
        if (!mounted) {
          ws.close();
          return;
        }
        handlersRef.current.onConnect?.();
      };

      ws.onclose = () => {
        // #region agent log H5 ws close
        fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H5", location: "useWsEvents.ts:onclose", message: "WebSocket closed", data: { wsUrl, readyState: ws.readyState }, timestamp: Date.now() }) }).catch(() => {});
        // #endregion
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
        if (mounted) {
          handlersRef.current.onDisconnect?.();
          // Reconnect after 2 seconds
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }
          reconnectTimeoutRef.current = setTimeout(connect, 2000);
        }
      };

      ws.onerror = () => {
        // #region agent log H5 ws error
        fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H5", location: "useWsEvents.ts:onerror", message: "WebSocket error event", data: { wsUrl, readyState: ws.readyState }, timestamp: Date.now() }) }).catch(() => {});
        // #endregion
      };

      ws.onmessage = (event) => {
        if (!mounted) return;

        try {
          const data = JSON.parse(event.data) as WsEvent;

          switch (data.type) {
            case "quote_update":
              handlersRef.current.onQuote?.(data);
              break;
            case "bar_update":
              handlersRef.current.onBar?.(data);
              break;
            case "market_status":
              handlersRef.current.onMarketStatus?.(data);
              break;
            case "execution_event":
              handlersRef.current.onExecution?.(data);
              break;
            case "heartbeat":
              handlersRef.current.onHeartbeat?.(data);
              break;
          }
        } catch {
          // Ignore parse errors
        }
      };
    };

    connect();

    return () => {
      mounted = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;

        if (ws.readyState === WebSocket.CONNECTING) {
          // Avoid noisy "closed before established" errors in React StrictMode cleanup.
          ws.addEventListener("open", () => ws.close(), { once: true });
        } else if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CLOSING) {
          ws.close();
        }
      }
    };
  }, [wsUrl]);

  return wsRef;
}
