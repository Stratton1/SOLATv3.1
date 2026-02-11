/**
 * Hook for monitoring IG broker status.
 * Polls /ig/status to determine configured + authenticated state.
 */

import { useState, useCallback, useEffect } from "react";
import { engineClient, IGStatusResponse } from "../lib/engineClient";

const POLL_INTERVAL_MS = 10000;

export function useIgStatus() {
  const [data, setData] = useState<IGStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const result = await engineClient.getIGStatus();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch IG status");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  return { data, isLoading, error, refetch: fetchStatus };
}
