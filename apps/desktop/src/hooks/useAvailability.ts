/**
 * Hook for fetching and managing data availability.
 */

import { useCallback, useEffect, useState } from "react";
import { engineClient } from "../lib/engineClient";

export function useAvailability() {
  const [availability, setAvailability] = useState<Record<string, string[]>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await engineClient.getDataAvailability();
      setAvailability(data);
    } catch (e) {
      console.error("Failed to load data availability:", e);
      setError(e instanceof Error ? e.message : "Failed to load availability");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const isTimeframeAvailable = useCallback((symbol: string, timeframe: string) => {
    const symbolTfs = availability[symbol];
    return symbolTfs ? symbolTfs.includes(timeframe) : false;
  }, [availability]);

  return {
    availability,
    isLoading,
    error,
    isTimeframeAvailable,
    refetch: fetch,
  };
}
