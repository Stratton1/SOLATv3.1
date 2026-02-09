/**
 * Hook for computing and managing chart overlays.
 *
 * Features:
 * - Debounced requests (250ms default) to prevent excessive API calls
 * - Respects performance mode settings
 */

import { useCallback, useEffect, useState, useMemo } from "react";
import {
  Bar,
  OverlayRequest,
  OverlayResult,
  engineClient,
} from "../lib/engineClient";
import { useDebounce } from "./useDebounce";

interface IndicatorConfig {
  type: string;
  params?: Record<string, number>;
}

interface UseOverlaysOptions {
  symbol: string;
  timeframe: string;
  indicators: IndicatorConfig[];
  bars?: Bar[];
  /** Debounce delay in ms (default 250) */
  debounceMs?: number;
}

interface UseOverlaysResult {
  overlays: OverlayResult[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useOverlays({
  symbol,
  timeframe,
  indicators,
  bars,
  debounceMs = 250,
}: UseOverlaysOptions): UseOverlaysResult {
  const [overlays, setOverlays] = useState<OverlayResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create stable indicator key for debouncing
  const indicatorKey = useMemo(
    () => JSON.stringify(indicators),
    [indicators]
  );

  // Debounce the request parameters
  const debouncedSymbol = useDebounce(symbol, debounceMs);
  const debouncedTimeframe = useDebounce(timeframe, debounceMs);
  const debouncedIndicatorKey = useDebounce(indicatorKey, debounceMs);
  const debouncedIndicators = useMemo(
    () => JSON.parse(debouncedIndicatorKey || "[]") as IndicatorConfig[],
    [debouncedIndicatorKey]
  );

  const fetch = useCallback(async () => {
    if (!debouncedSymbol || !debouncedTimeframe || debouncedIndicators.length === 0) {
      setOverlays([]);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const request: OverlayRequest = {
        symbol: debouncedSymbol,
        timeframe: debouncedTimeframe,
        indicators: debouncedIndicators,
        bars,
      };
      const data = await engineClient.computeOverlays(request);
      setOverlays(data.overlays);
    } catch (e) {
      // Handle rate limit (429) gracefully
      if (e instanceof Error && e.message.includes("429")) {
        setError("Rate limit exceeded. Please wait.");
      } else {
        setError(e instanceof Error ? e.message : "Failed to compute overlays");
      }
    } finally {
      setIsLoading(false);
    }
  }, [debouncedSymbol, debouncedTimeframe, debouncedIndicators, bars]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return {
    overlays,
    isLoading,
    error,
    refetch: fetch,
  };
}
