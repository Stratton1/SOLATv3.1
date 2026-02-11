/**
 * Hook for fetching trading signals.
 */

import { useCallback, useEffect, useState, useRef } from "react";
import { Signal, engineClient } from "../lib/engineClient";

const DEBUG_INGEST_URL = "http://127.0.0.1:7245/ingest/b34e6a51-242b-4280-9e50-b775760b6116";

interface UseSignalsOptions {
  symbol: string;
  timeframe: string;
  startTs?: string;
  endTs?: string;
  enabled?: boolean;
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
  enabled = true,
}: UseSignalsOptions): UseSignalsResult {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetch = useCallback(async () => {
    if (!enabled || !symbol || !timeframe) {
      setSignals([]);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);
    try {
      // #region agent log H4 signal request cadence
      globalThis.fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H4", location: "useSignals.ts:fetch:request", message: "Signals request prepared", data: { symbol, timeframe, hasStart: Boolean(startTs), hasEnd: Boolean(endTs) }, timestamp: Date.now() }) }).catch(() => {});
      // #endregion
      const data = await engineClient.getSignals({
        symbol,
        timeframe,
        start_ts: startTs,
        end_ts: endTs,
      });
      if (controller.signal.aborted) return;
      setSignals(data.signals);
    } catch (e) {
      if (controller.signal.aborted) return;
      // #region agent log H4 signal failure
      globalThis.fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H4", location: "useSignals.ts:fetch:error", message: "Signals request failed", data: { error: e instanceof Error ? e.message : String(e) }, timestamp: Date.now() }) }).catch(() => {});
      // #endregion
      setError(e instanceof Error ? e.message : "Failed to load signals");
    } finally {
      if (!controller.signal.aborted) setIsLoading(false);
    }
  }, [symbol, timeframe, startTs, endTs, enabled]);

  useEffect(() => {
    fetch();
    return () => abortRef.current?.abort();
  }, [fetch]);

  return {
    signals,
    isLoading,
    error,
    refetch: fetch,
  };
}
