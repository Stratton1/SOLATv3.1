/**
 * Hook for monitoring engine health with retry logic and backoff.
 *
 * Provides:
 * - Automatic reconnection with exponential backoff
 * - Connection state tracking
 * - Manual retry trigger
 */

import { useCallback, useEffect, useRef, useState } from "react";

const ENGINE_URL = "http://127.0.0.1:8765";

// Retry configuration
const INITIAL_DELAY_MS = 3000; // Wait for engine to start before first check
const INITIAL_RETRY_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 30000;
const BACKOFF_MULTIPLIER = 1.5;
const POLL_INTERVAL_MS = 5000;

export interface HealthData {
  status: string;
  version: string;
  time: string;
  uptime_seconds: number;
}

export interface ConfigData {
  mode: string;
  env: string;
  data_dir: string;
  app_env: string;
  ig_configured: boolean;
}

export type ConnectionState =
  | "connecting"
  | "connected"
  | "disconnected"
  | "retrying";

export interface UseEngineHealthResult {
  health: HealthData | null;
  config: ConfigData | null;
  isLoading: boolean;
  error: string | null;
  connectionState: ConnectionState;
  retryCount: number;
  nextRetryIn: number | null;
  refetch: () => void;
  manualRetry: () => void;
}

export function useEngineHealth(): UseEngineHealthResult {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting");
  const [retryCount, setRetryCount] = useState(0);
  const [nextRetryIn, setNextRetryIn] = useState<number | null>(null);

  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Track whether we've ever successfully fetched, to avoid loading jitter on polls
  const hasDataRef = useRef(false);

  const clearTimers = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
  }, []);

  const scheduleRetry = useCallback(
    (attempt: number) => {
      const delay = Math.min(
        INITIAL_RETRY_DELAY_MS * Math.pow(BACKOFF_MULTIPLIER, attempt),
        MAX_RETRY_DELAY_MS
      );

      setConnectionState("retrying");
      setNextRetryIn(Math.ceil(delay / 1000));

      // Start countdown
      countdownIntervalRef.current = setInterval(() => {
        setNextRetryIn((prev) => {
          if (prev === null || prev <= 1) {
            if (countdownIntervalRef.current) {
              clearInterval(countdownIntervalRef.current);
            }
            return null;
          }
          return prev - 1;
        });
      }, 1000);

      retryTimeoutRef.current = setTimeout(() => {
        fetchData();
      }, delay);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const fetchData = useCallback(async () => {
    try {
      // Only show loading spinner on initial fetch (no existing data).
      // Subsequent polls keep stale data visible ("stale-while-revalidate").
      if (!hasDataRef.current) {
        setIsLoading(true);
      }
      setError(null);

      if (connectionState === "disconnected" || connectionState === "retrying") {
        setConnectionState("connecting");
      }

      // Fetch health and config in parallel with timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      const [healthRes, configRes] = await Promise.all([
        fetch(`${ENGINE_URL}/health`, { signal: controller.signal }),
        fetch(`${ENGINE_URL}/config`, { signal: controller.signal }),
      ]);

      clearTimeout(timeoutId);

      if (!healthRes.ok || !configRes.ok) {
        throw new Error("Failed to fetch engine status");
      }

      const healthData = await healthRes.json();
      const configData = await configRes.json();

      setHealth(healthData);
      setConfig(configData);
      setConnectionState("connected");
      setRetryCount(0);
      setNextRetryIn(null);
      hasDataRef.current = true;

      // Start polling if not already
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(fetchData, POLL_INTERVAL_MS);
      }
    } catch (err) {
      const message =
        err instanceof Error
          ? err.name === "AbortError"
            ? "Connection timeout"
            : err.message
          : "Unknown error";

      setError(message);
      // Keep stale data visible so cards don't blank out during transient errors.
      if (!hasDataRef.current) {
        setHealth(null);
        setConfig(null);
      }
      setConnectionState("disconnected");

      // Clear polling
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }

      // Schedule retry with backoff
      const newRetryCount = retryCount + 1;
      setRetryCount(newRetryCount);
      scheduleRetry(newRetryCount);
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionState, retryCount]);

  const manualRetry = useCallback(() => {
    clearTimers();
    setRetryCount(0);
    setNextRetryIn(null);
    fetchData();
  }, [clearTimers, fetchData]);

  useEffect(() => {
    // Delay first health check to give engine time to start
    const initialTimer = setTimeout(() => {
      fetchData();
    }, INITIAL_DELAY_MS);

    return () => {
      clearTimeout(initialTimer);
      clearTimers();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    health,
    config,
    isLoading,
    error,
    connectionState,
    retryCount,
    nextRetryIn,
    refetch: fetchData,
    manualRetry,
  };
}

export default useEngineHealth;
