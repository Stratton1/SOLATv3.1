/**
 * Hook for computing and managing chart overlays.
 *
 * Features:
 * - Debounced requests (250ms default) to prevent excessive API calls
 * - Respects performance mode settings
 */

import { useCallback, useEffect, useState, useMemo, useRef } from "react";
import {
  OverlayRequest,
  OverlayResult,
  engineClient,
} from "../lib/engineClient";
import { useDebounce } from "./useDebounce";

const DEBUG_INGEST_URL = "http://127.0.0.1:7245/ingest/b34e6a51-242b-4280-9e50-b775760b6116";

interface IndicatorConfig {
  type: string;
  params?: Record<string, number>;
}

function toEngineIndicator(indicator: IndicatorConfig): string {
  const type = indicator.type.toLowerCase();
  const params = indicator.params ?? {};

  if (type === "ema" || type === "sma" || type === "rsi" || type === "atr") {
    const period = params.period ?? 14;
    return `${type}_${period}`;
  }
  if (type === "macd") {
    const fast = params.fast ?? 12;
    const slow = params.slow ?? 26;
    const signal = params.signal ?? 9;
    return `${type}_${fast}_${slow}_${signal}`;
  }
  if (type === "bb" || type === "bollinger") {
    const period = params.period ?? 20;
    const stdDev = params.std_dev ?? params.stdDev ?? 2;
    return `bb_${period}_${stdDev}`;
  }
  if (type === "stoch" || type === "stochastic") {
    const kPeriod = params.k_period ?? params.kPeriod ?? 14;
    const dPeriod = params.d_period ?? params.dPeriod ?? 3;
    return `stoch_${kPeriod}_${dPeriod}`;
  }
  if (type === "ichimoku") {
    return "ichimoku";
  }
  return type;
}

interface UseOverlaysOptions {
  symbol: string;
  timeframe: string;
  indicators: IndicatorConfig[];
  /** Debounce delay in ms (default 250) */
  debounceMs?: number;
}

interface UseOverlaysResult {
  overlays: OverlayResult[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

function normalizeOverlayResponse(data: unknown): OverlayResult[] {
  if (!data || typeof data !== "object") return [];
  const overlays = (data as { overlays?: unknown[] }).overlays;
  if (!Array.isArray(overlays)) return [];

  return overlays.flatMap((raw): OverlayResult[] => {
    if (!raw || typeof raw !== "object") return [];
    if ("values" in raw) return [raw as OverlayResult];

    const legacy = raw as { type?: string; data?: Array<Record<string, unknown>> };
    if (!legacy.type || !Array.isArray(legacy.data)) return [];

    const values: Record<string, Array<{ ts: string; value: number | null }>> = {};
    for (const point of legacy.data) {
      const ts = typeof point.ts === "string" ? point.ts : null;
      if (!ts) continue;
      for (const [key, value] of Object.entries(point)) {
        if (key === "ts") continue;
        if (!values[key]) values[key] = [];
        values[key].push({ ts, value: typeof value === "number" ? value : null });
      }
    }

    return [{ type: legacy.type, params: {}, values }];
  });
}

export function useOverlays({
  symbol,
  timeframe,
  indicators,
  debounceMs = 250,
}: UseOverlaysOptions): UseOverlaysResult {
  const [overlays, setOverlays] = useState<OverlayResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);
    try {
      const request: OverlayRequest = {
        symbol: debouncedSymbol,
        timeframe: debouncedTimeframe,
        indicators: debouncedIndicators.map(toEngineIndicator),
        limit: 500,
      };
      // #region agent log H2 payload shape
      globalThis.fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H2", location: "useOverlays.ts:fetch:request", message: "Overlay request prepared", data: { symbol: debouncedSymbol, timeframe: debouncedTimeframe, indicatorCount: debouncedIndicators.length, indicatorSample: debouncedIndicators.slice(0, 3) }, timestamp: Date.now() }) }).catch(() => {});
      // #endregion
      const data = await engineClient.computeOverlays(request);
      if (controller.signal.aborted) return;
      setOverlays(normalizeOverlayResponse(data));
    } catch (e) {
      if (controller.signal.aborted) return;
      // #region agent log H2 overlay failure
      globalThis.fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H2", location: "useOverlays.ts:fetch:error", message: "Overlay request failed", data: { error: e instanceof Error ? e.message : String(e) }, timestamp: Date.now() }) }).catch(() => {});
      // #endregion
      // Handle rate limit (429) gracefully
      if (e instanceof Error && e.message.includes("429")) {
        setError("Rate limit exceeded. Please wait.");
      } else {
        setError(e instanceof Error ? e.message : "Failed to compute overlays");
      }
    } finally {
      if (!controller.signal.aborted) setIsLoading(false);
    }
  }, [debouncedSymbol, debouncedTimeframe, debouncedIndicators]);

  useEffect(() => {
    fetch();
    return () => abortRef.current?.abort();
  }, [fetch]);

  return {
    overlays,
    isLoading,
    error,
    refetch: fetch,
  };
}
