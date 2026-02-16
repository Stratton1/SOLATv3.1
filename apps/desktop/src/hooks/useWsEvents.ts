/**
 * Hook for handling WebSocket events with typed handlers.
 */

import { useEffect, useRef } from "react";
import { Bar } from "../lib/engineClient";
import { useEngineConnection } from "../context/EngineConnectionContext";

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
  onQuote?: (event: QuoteUpdateEvent) => void;
  onBar?: (event: BarUpdateEvent) => void;
  onMarketStatus?: (event: MarketStatusEvent) => void;
  onExecution?: (event: ExecutionEvent) => void;
  onHeartbeat?: (event: HeartbeatEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

export function useWsEvents({
  onQuote,
  onBar,
  onMarketStatus,
  onExecution,
  onHeartbeat,
  onConnect,
  onDisconnect,
}: UseWsEventsOptions) {
  const { isConnected, lastMessage } = useEngineConnection();
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
    if (!lastMessage || typeof lastMessage !== "object") return;
    const data = lastMessage as WsEvent | Record<string, unknown>;
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
      case "order_event":
      case "position_event":
        handlersRef.current.onExecution?.({
          type: "execution_event",
          event_type: eventType,
          data: data as Record<string, unknown>,
        });
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
      default:
        break;
    }
  }, [lastMessage]);

  const prevConnectedRef = useRef<boolean>(false);
  useEffect(() => {
    if (isConnected && !prevConnectedRef.current) {
      handlersRef.current.onConnect?.();
    }
    if (!isConnected && prevConnectedRef.current) {
      handlersRef.current.onDisconnect?.();
    }
    prevConnectedRef.current = isConnected;
  }, [isConnected]);
}
