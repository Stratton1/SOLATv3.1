/**
 * Hook for fetching trading signals.
 */

import { useCallback, useEffect, useState } from "react";
import { Signal, engineClient } from "../lib/engineClient";

interface UseSignalsOptions {
  symbol: string;
  timeframe: string;
  startTs?: string;
  endTs?: string;
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
}: UseSignalsOptions): UseSignalsResult {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!symbol || !timeframe) {
      setSignals([]);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const data = await engineClient.getSignals({
        symbol,
        timeframe,
        start_ts: startTs,
        end_ts: endTs,
      });
      setSignals(data.signals);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load signals");
    } finally {
      setIsLoading(false);
    }
  }, [symbol, timeframe, startTs, endTs]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return {
    signals,
    isLoading,
    error,
    refetch: fetch,
  };
}
