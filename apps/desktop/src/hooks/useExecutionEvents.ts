/**
 * Hook to fetch execution events (fills, orders) for chart markers.
 */

import { useState, useEffect, useCallback } from "react";
import {
  engineClient,
  ExecutionFill,
  OpenPosition,
} from "../lib/engineClient";
import { Execution, SlTpLevel } from "../components/CandleChart";

const DEBUG_INGEST_URL = "http://127.0.0.1:7245/ingest/b34e6a51-242b-4280-9e50-b775760b6116";

interface UseExecutionEventsOptions {
  symbol: string;
  enabled?: boolean;
}

interface UseExecutionEventsResult {
  executions: Execution[];
  slTpLevels: SlTpLevel[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useExecutionEvents({
  symbol,
  enabled = true,
}: UseExecutionEventsOptions): UseExecutionEventsResult {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [slTpLevels, setSlTpLevels] = useState<SlTpLevel[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!symbol || !enabled) return;

    setIsLoading(true);
    setError(null);

    try {
      // #region agent log H3 positions preflight
      fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H3", location: "useExecutionEvents.ts:fetch:start", message: "Execution events fetch start", data: { symbol, enabled }, timestamp: Date.now() }) }).catch(() => {});
      // #endregion
      const state = await engineClient.getExecutionState().catch(() => null);
      if (!state?.connected) {
        setExecutions([]);
        setSlTpLevels([]);
        return;
      }
      // Fetch fills and positions in parallel
      const [fillsRes, positionsRes] = await Promise.all([
        engineClient.getExecutionFills({ symbol, limit: 200 }).catch(() => null),
        engineClient.getPositions().catch(() => null),
      ]);
      // #region agent log H3 positions result
      fetch(DEBUG_INGEST_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ runId: "pre-fix", hypothesisId: "H3", location: "useExecutionEvents.ts:fetch:result", message: "Execution events fetch result", data: { fillsReturned: Boolean(fillsRes), positionsReturned: Boolean(positionsRes), fillsCount: fillsRes?.fills?.length ?? 0, positionsCount: positionsRes?.positions?.length ?? 0 }, timestamp: Date.now() }) }).catch(() => {});
      // #endregion

      // Convert fills to execution markers
      if (fillsRes) {
        const mapped: Execution[] = fillsRes.fills.map((fill: ExecutionFill) => ({
          ts: fill.ts,
          type: fill.is_close ? "EXIT" as const : "ENTRY" as const,
          direction: (fill.side ?? fill.direction ?? "BUY"),
          price: fill.price,
          size: fill.size,
          bot: fill.bot,
        }));
        setExecutions(mapped);
      }

      // Extract SL/TP levels from open positions
      if (positionsRes) {
        const levels: SlTpLevel[] = [];
        positionsRes.positions
          .filter((p: OpenPosition) => p.symbol === symbol)
          .forEach((pos: OpenPosition) => {
            const slPrice = pos.sl_price ?? pos.stop_level;
            const tpPrice = pos.tp_price ?? pos.limit_level;
            if (slPrice) {
              levels.push({
                type: "SL",
                price: slPrice,
                direction: pos.direction,
                symbol: pos.symbol,
              });
            }
            if (tpPrice) {
              levels.push({
                type: "TP",
                price: tpPrice,
                direction: pos.direction,
                symbol: pos.symbol,
              });
            }
          });
        setSlTpLevels(levels);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch execution data");
    } finally {
      setIsLoading(false);
    }
  }, [symbol, enabled]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Refresh on 30s interval when enabled
  useEffect(() => {
    if (!enabled) return;
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData, enabled]);

  return { executions, slTpLevels, isLoading, error, refresh: fetchData };
}
