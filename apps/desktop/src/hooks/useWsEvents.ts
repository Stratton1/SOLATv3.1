/**
 * Hook for handling WebSocket events with typed handlers.
 */

import { useEffect, useRef } from "react";
import { Bar } from "../lib/engineClient";

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

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mounted) {
          ws.close();
          return;
        }
        handlersRef.current.onConnect?.();
      };

      ws.onclose = () => {
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
        // Will trigger onclose — no additional handling needed
      };

      ws.onmessage = (event) => {
        if (!mounted) return;

        try {
          const data = JSON.parse(event.data) as WsEvent | Record<string, unknown>;
          const eventType = typeof data.type === "string" ? data.type : "";

          switch (eventType) {
            case "quote_update":
              handlersRef.current.onQuote?.(data as QuoteUpdateEvent);
              break;
            case "bar_update":
              handlersRef.current.onBar?.(data as BarUpdateEvent);
              break;
            case "market_status":
              handlersRef.current.onMarketStatus?.(data as MarketStatusEvent);
              break;
            case "execution_event":
              handlersRef.current.onExecution?.(data as ExecutionEvent);
              break;
            case "execution.status":
            case "execution.intent_created":
            case "execution.order_submitted":
            case "execution.order_rejected":
            case "execution.order_acknowledged":
            case "execution.positions_updated":
            case "execution.reconciliation_warning":
            case "execution.kill_switch_activated":
            case "execution.kill_switch_reset":
              handlersRef.current.onExecution?.({
                type: "execution_event",
                event_type: eventType,
                data: data as Record<string, unknown>,
              });
              break;
            case "heartbeat":
            case "system.heartbeat":
              handlersRef.current.onHeartbeat?.(data as HeartbeatEvent);
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
