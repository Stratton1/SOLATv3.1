import { useCallback, useEffect, useRef, useState } from "react";
import { engineClient } from "../lib/engineClient";

const POLL_INTERVAL_MS = 5000;

export interface BrokerMetrics {
  last_request_latency_ms: number;
  average_latency_ms: number;
  rate_limit_usage_pct: number;
}

export interface IGStatusResponse {
  configured: boolean;
  mode: string;
  base_url: string | null;
  authenticated: boolean;
  session_age_seconds: number | null;
  session_expiry_ts: string | null;
  rate_limiter: Record<string, unknown>;
  metrics: BrokerMetrics;
}

export function useBrokerStatus() {
  const [data, setData] = useState<IGStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const started = performance.now();
      const [config, account] = await Promise.all([
        engineClient.getConfig(),
        engineClient.getAccount(),
      ]);
      const latency = Math.max(1, Math.round(performance.now() - started));
      const statusData: IGStatusResponse = {
        configured: Boolean(config.ig_configured),
        mode: config.execution_mode ?? config.mode ?? "DEMO",
        base_url: null,
        authenticated: true,
        session_age_seconds: null,
        session_expiry_ts: null,
        rate_limiter: {},
        metrics: {
          last_request_latency_ms: latency,
          average_latency_ms: latency,
          rate_limit_usage_pct: 0,
        },
      };
      if (!account.account_id) {
        statusData.authenticated = false;
      }
      setData(statusData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setData({
        configured: false,
        mode: "DEMO",
        base_url: null,
        authenticated: false,
        session_age_seconds: null,
        session_expiry_ts: null,
        rate_limiter: {},
        metrics: {
          last_request_latency_ms: 0,
          average_latency_ms: 0,
          rate_limit_usage_pct: 0,
        },
      });
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
