import { useCallback, useEffect, useRef, useState } from "react";

const WS_URL = "ws://127.0.0.1:8765/ws";
const RECONNECT_DELAY = 2000;
const MAX_RECONNECT_ATTEMPTS = 10;

interface UseWebSocketResult {
  heartbeatCount: number;
  isConnected: boolean;
  connectionStatus: string;
  lastMessage: unknown;
}

export function useWebSocket(): UseWebSocketResult {
  const [heartbeatCount, setHeartbeatCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState("Connecting...");
  const [lastMessage, setLastMessage] = useState<unknown>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    try {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        console.log("[WebSocket] Connected");
        setIsConnected(true);
        setConnectionStatus("Connected");
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLastMessage(data);

          if (data.type === "heartbeat") {
            setHeartbeatCount(data.count);
          }
        } catch (err) {
          console.error("[WebSocket] Failed to parse message:", err);
        }
      };

      ws.onclose = (event) => {
        console.log("[WebSocket] Disconnected:", event.code, event.reason);
        setIsConnected(false);
        wsRef.current = null;

        // Attempt reconnect
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current += 1;
          setConnectionStatus(
            `Reconnecting (${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})...`
          );

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, RECONNECT_DELAY);
        } else {
          setConnectionStatus("Disconnected");
        }
      };

      ws.onerror = (error) => {
        console.error("[WebSocket] Error:", error);
        setConnectionStatus("Connection error");
      };

      wsRef.current = ws;
    } catch (err) {
      console.error("[WebSocket] Failed to create connection:", err);
      setConnectionStatus("Failed to connect");
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      // Cleanup on unmount
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { heartbeatCount, isConnected, connectionStatus, lastMessage };
}
