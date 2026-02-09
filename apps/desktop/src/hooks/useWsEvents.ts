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
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    let mounted = true;

    const connect = () => {
      if (!mounted) return;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (mounted) {
          onConnect?.();
        }
      };

      ws.onclose = () => {
        if (mounted) {
          onDisconnect?.();
          // Reconnect after 2 seconds
          reconnectTimeoutRef.current = setTimeout(connect, 2000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onmessage = (event) => {
        if (!mounted) return;

        try {
          const data = JSON.parse(event.data) as WsEvent;

          switch (data.type) {
            case "quote_update":
              onQuote?.(data);
              break;
            case "bar_update":
              onBar?.(data);
              break;
            case "market_status":
              onMarketStatus?.(data);
              break;
            case "execution_event":
              onExecution?.(data);
              break;
            case "heartbeat":
              onHeartbeat?.(data);
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
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [wsUrl, onQuote, onBar, onMarketStatus, onExecution, onHeartbeat, onConnect, onDisconnect]);

  return wsRef;
}
