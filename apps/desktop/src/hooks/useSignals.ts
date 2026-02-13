/**
 * Hook for fetching trading signals from strategies.
 */

import { useCallback, useEffect, useState, useRef } from "react";
import { Signal, engineClient } from "../lib/engineClient";

interface UseSignalsOptions {
  symbol: string;
  timeframe: string;
  startTs?: string;
  endTs?: string;
  strategies?: string[];
  enabled?: boolean;
  debounceMs?: number;
}

interface UseSignalsResult {
  signals: Signal[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useSignals({
  symbol,
  timeframe,
  startTs,
  endTs,
  strategies,
  enabled = true,
  debounceMs = 500,
}: UseSignalsOptions): UseSignalsResult {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSignals = useCallback(async () => {
    if (!enabled || !symbol || !timeframe) {
      setSignals([]);
      return;
    }

    // No strategies selected — clear signals
    if (!strategies || strategies.length === 0) {
      setSignals([]);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);
    try {
      const data = await engineClient.getSignals({
        symbol,
        timeframe,
        start_ts: startTs,
        end_ts: endTs,
        strategies,
      });
      if (controller.signal.aborted) return;
      setSignals(data.signals);
    } catch (e) {
      if (controller.signal.aborted) return;
      setError(e instanceof Error ? e.message : "Failed to load signals");
    } finally {
      if (!controller.signal.aborted) setIsLoading(false);
    }
  }, [symbol, timeframe, startTs, endTs, strategies, enabled]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchSignals();
    }, debounceMs);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      abortRef.current?.abort();
    };
  }, [fetchSignals, debounceMs]);

  return {
    signals,
    isLoading,
    error,
    refetch: fetchSignals,
  };
}
