import { useCallback, useEffect, useRef, useState } from "react";

const ENGINE_URL = "http://127.0.0.1:8765";
const POLL_INTERVAL_MS = 5000;

export interface BrokerMetrics {
  last_request_latency_ms: number;
  average_latency_ms: number;
  rate_limit_usage_pct: number;
}

export interface IGStatusResponse {
  configured: boolean;
  mode: string;
  base_url: string;
  authenticated: boolean;
  session_age_seconds: number | null;
  session_expiry_ts: string | null;
  rate_limiter: Record<string, any>;
  metrics: BrokerMetrics;
}

export function useBrokerStatus() {
  const [data, setData] = useState<IGStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/ig/status`);
      if (!res.ok) {
        throw new Error("Failed to fetch IG status");
      }
      const statusData = await res.json();
      setData(statusData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    pollIntervalRef.current = setInterval(fetchStatus, POLL_INTERVAL_MS);
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchStatus]);

  return { data, isLoading, error, refetch: fetchStatus };
}
