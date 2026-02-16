/**
 * Hook for fetching and managing bar data.
 */

import { useCallback, useEffect, useState, useRef } from "react";
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
  isLoadingHistory: boolean;
  error: string | null;
  quality: BarsResponse["quality"];
  start: string | null;
  end: string | null;
  requestedLimit: number | null;
  coveragePct: number | null;
  source: string | null;
  hasMoreHistory: boolean;
  refetch: () => void;
  appendBar: (bar: Bar) => void;
  loadOlderBars: (chunkSize?: number) => Promise<number>;
}

export function useBars({
  symbol,
  timeframe,
  limit = 2000,
  autoRefresh = false,
  refreshInterval = 60000,
}: UseBarsOptions): UseBarsResult {
  const [bars, setBars] = useState<Bar[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quality, setQuality] = useState<BarsResponse["quality"]>(undefined);
  const [start, setStart] = useState<string | null>(null);
  const [end, setEnd] = useState<string | null>(null);
  const [requestedLimit, setRequestedLimit] = useState<number | null>(null);
  const [coveragePct, setCoveragePct] = useState<number | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [hasMoreHistory, setHasMoreHistory] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  const fetch = useCallback(async () => {
    if (!symbol || !timeframe) return;

    // Cancel previous in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);
    try {
      const data = await engineClient.getBars(symbol, timeframe, { limit });
      if (controller.signal.aborted) return;
      setBars(data.bars);
      setQuality(data.quality);
      setStart(data.start ?? null);
      setEnd(data.end ?? null);
      setRequestedLimit(data.requested_limit ?? null);
      setCoveragePct(data.coverage_pct ?? null);
      setSource(data.source ?? null);
      setHasMoreHistory(true);
    } catch (e) {
      if (controller.signal.aborted) return;
      setError(e instanceof Error ? e.message : "Failed to load bars");
    } finally {
      if (!controller.signal.aborted) setIsLoading(false);
    }
  }, [symbol, timeframe, limit]);

  useEffect(() => {
    fetch();
    return () => abortRef.current?.abort();
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

  const loadOlderBars = useCallback(
    async (chunkSize: number = 1000): Promise<number> => {
      if (!symbol || !timeframe || isLoadingHistory || !hasMoreHistory || bars.length === 0) {
        return 0;
      }
      const earliestTs = bars[0].ts;
      setIsLoadingHistory(true);
      try {
        const data = await engineClient.getBars(symbol, timeframe, {
          end: earliestTs,
          limit: chunkSize,
        });
        const older = data.bars.filter((b) => b.ts < earliestTs);
        if (older.length === 0) {
          setHasMoreHistory(false);
          return 0;
        }
        setBars((prev) => {
          const map = new Map<string, Bar>();
          for (const b of [...older, ...prev]) map.set(b.ts, b);
          return Array.from(map.values()).sort((a, b) => a.ts.localeCompare(b.ts));
        });
        setStart((prev) => older[0]?.ts ?? prev);
        return older.length;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load older bars");
        return 0;
      } finally {
        setIsLoadingHistory(false);
      }
    },
    [bars, hasMoreHistory, isLoadingHistory, symbol, timeframe]
  );

  return {
    bars,
    isLoading,
    isLoadingHistory,
    error,
    quality,
    start,
    end,
    requestedLimit,
    coveragePct,
    source,
    hasMoreHistory,
    refetch: fetch,
    appendBar,
    loadOlderBars,
  };
}
