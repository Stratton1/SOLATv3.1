/**
 * Hook for fetching engine diagnostics.
 */

import { useCallback, useEffect, useState } from "react";
import { DiagnosticsFull, engineClient } from "../lib/engineClient";

interface UseDiagnosticsResult {
  diagnostics: DiagnosticsFull | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Fetch all diagnostics from the engine.
 *
 * @param autoRefresh - Whether to auto-refresh (default false)
 * @param refreshInterval - Refresh interval in ms (default 5000)
 */
export function useDiagnostics(
  autoRefresh = false,
  refreshInterval = 5000
): UseDiagnosticsResult {
  const [diagnostics, setDiagnostics] = useState<DiagnosticsFull | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await engineClient.getDiagnosticsAll();
      setDiagnostics(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch diagnostics");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(fetch, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, fetch]);

  return {
    diagnostics,
    isLoading,
    error,
    refetch: fetch,
  };
}
