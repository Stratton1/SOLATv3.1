import { useCallback, useEffect, useRef, useState } from "react";

const WS_URL = "ws://127.0.0.1:8765/ws";
const INITIAL_DELAY_MS = 3000; // Wait for engine to start before first attempt
const MIN_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 15000;
const BACKOFF_MULTIPLIER = 1.5;

interface UseWebSocketResult {
  heartbeatCount: number;
  isConnected: boolean;
  connectionStatus: string;
  lastMessage: unknown;
}

export function useWebSocket(): UseWebSocketResult {
  const [heartbeatCount, setHeartbeatCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState("Waiting for engine...");
  const [lastMessage, setLastMessage] = useState<unknown>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.onclose = null; // Prevent reconnect loop from close handler
      wsRef.current.close();
      wsRef.current = null;
    }

    try {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        setConnectionStatus("Connected");
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const data = JSON.parse(event.data);
          setLastMessage(data);

          if (data.type === "heartbeat") {
            setHeartbeatCount(data.count);
          }
        } catch {
          // Ignore parse errors
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        wsRef.current = null;

        // Always reconnect with backoff — never give up
        reconnectAttemptsRef.current += 1;
        const delay = Math.min(
          MIN_RECONNECT_DELAY * Math.pow(BACKOFF_MULTIPLIER, reconnectAttemptsRef.current - 1),
          MAX_RECONNECT_DELAY
        );

        setConnectionStatus(
          `Reconnecting (${reconnectAttemptsRef.current})...`
        );

        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      };

      ws.onerror = () => {
        // Suppress — onclose will handle reconnection
        if (!isConnected) {
          setConnectionStatus("Waiting for engine...");
        }
      };

      wsRef.current = ws;
    } catch {
      // Connection creation failed — schedule retry
      if (!mountedRef.current) return;
      reconnectAttemptsRef.current += 1;
      const delay = Math.min(
        MIN_RECONNECT_DELAY * Math.pow(BACKOFF_MULTIPLIER, reconnectAttemptsRef.current - 1),
        MAX_RECONNECT_DELAY
      );
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
    }
  }, [isConnected]);

  useEffect(() => {
    mountedRef.current = true;

    // Delay initial connection to give engine time to start
    const initialTimer = setTimeout(() => {
      connect();
    }, INITIAL_DELAY_MS);

    return () => {
      mountedRef.current = false;
      clearTimeout(initialTimer);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { heartbeatCount, isConnected, connectionStatus, lastMessage };
}
