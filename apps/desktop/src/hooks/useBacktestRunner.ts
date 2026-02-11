/**
 * Hook for triggering and polling backtest runs.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { engineClient, BacktestRequest, BacktestStatusResponse } from "../lib/engineClient";

interface UseBacktestRunnerResult {
  runId: string | null;
  status: BacktestStatusResponse | null;
  isRunning: boolean;
  error: string | null;
  startBacktest: (request: BacktestRequest) => Promise<void>;
  reset: () => void;
}

const POLL_INTERVAL_MS = 2000;

export function useBacktestRunner(): UseBacktestRunnerResult {
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<BacktestStatusResponse | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startBacktest = useCallback(
    async (request: BacktestRequest) => {
      try {
        setError(null);
        setIsRunning(true);
        setStatus(null);

        const response = await engineClient.startBacktest(request);
        if (!response.ok) {
          throw new Error(response.message || "Failed to start backtest");
        }

        setRunId(response.run_id);

        // Start polling for status
        pollRef.current = setInterval(async () => {
          try {
            const s = await engineClient.getBacktestStatus(response.run_id);
            setStatus(s);

            if (s.status === "done" || s.status === "failed") {
              stopPolling();
              setIsRunning(false);
              if (s.status === "failed") {
                const detail = s.error_type
                  ? `${s.error_type}: ${s.error_message ?? s.message}`
                  : s.message || "Backtest failed";
                setError(detail);
              }
            }
          } catch {
            // Ignore polling errors
          }
        }, POLL_INTERVAL_MS);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start backtest");
        setIsRunning(false);
      }
    },
    [stopPolling]
  );

  const reset = useCallback(() => {
    stopPolling();
    setRunId(null);
    setStatus(null);
    setIsRunning(false);
    setError(null);
  }, [stopPolling]);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  return { runId, status, isRunning, error, startBacktest, reset };
}
