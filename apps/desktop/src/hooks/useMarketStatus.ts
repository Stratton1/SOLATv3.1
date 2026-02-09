/**
 * Hook for market data stream status.
 */

import { useCallback, useEffect, useState } from "react";
import { MarketStatus, engineClient } from "../lib/engineClient";

interface UseMarketStatusResult {
  status: MarketStatus | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useMarketStatus(pollInterval = 5000): UseMarketStatusResult {
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    try {
      const data = await engineClient.getMarketStatus();
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to get market status");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
    const interval = setInterval(fetch, pollInterval);
    return () => clearInterval(interval);
  }, [fetch, pollInterval]);

  return {
    status,
    isLoading,
    error,
    refetch: fetch,
  };
}
