/**
 * Hook for fetching and managing bar data.
 */

import { useCallback, useEffect, useState } from "react";
import { Bar, BarsResponse, engineClient } from "../lib/engineClient";

interface UseBarsOptions {
  symbol: string;
  timeframe: string;
  limit?: number;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

interface UseBarsResult {
  bars: Bar[];
  isLoading: boolean;
  error: string | null;
  quality: BarsResponse["quality"];
  start: string | null;
  end: string | null;
  refetch: () => void;
  appendBar: (bar: Bar) => void;
}

export function useBars({
  symbol,
  timeframe,
  limit = 500,
  autoRefresh = false,
  refreshInterval = 60000,
}: UseBarsOptions): UseBarsResult {
  const [bars, setBars] = useState<Bar[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quality, setQuality] = useState<BarsResponse["quality"]>(undefined);
  const [start, setStart] = useState<string | null>(null);
  const [end, setEnd] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!symbol || !timeframe) return;

    setIsLoading(true);
    setError(null);
    try {
      const data = await engineClient.getBars(symbol, timeframe, { limit });
      setBars(data.bars);
      setQuality(data.quality);
      setStart(data.start ?? null);
      setEnd(data.end ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load bars");
    } finally {
      setIsLoading(false);
    }
  }, [symbol, timeframe, limit]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetch, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, fetch]);

  const appendBar = useCallback((bar: Bar) => {
    setBars((prev) => {
      // Check if this bar updates the last bar or is a new bar
      if (prev.length === 0) return [bar];

      const lastBar = prev[prev.length - 1];
      if (lastBar.ts === bar.ts) {
        // Update existing bar
        return [...prev.slice(0, -1), bar];
      } else {
        // Append new bar
        return [...prev, bar];
      }
    });
  }, []);

  return {
    bars,
    isLoading,
    error,
    quality,
    start,
    end,
    refetch: fetch,
    appendBar,
  };
}
