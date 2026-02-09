/**
 * Hook for fetching backtest runs list.
 */

import { useState, useEffect, useCallback } from "react";
import {
  engineClient,
  BacktestRunSummary,
} from "../lib/engineClient";

interface UseBacktestRunsResult {
  runs: BacktestRunSummary[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useBacktestRuns(): UseBacktestRunsResult {
  const [runs, setRuns] = useState<BacktestRunSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await engineClient.listBacktestRuns();
      setRuns(response.runs);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to fetch backtest runs";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  return {
    runs,
    isLoading,
    error,
    refetch: fetchRuns,
  };
}
