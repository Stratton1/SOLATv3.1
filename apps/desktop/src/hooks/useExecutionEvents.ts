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
      // Fetch fills and positions in parallel
      const [fillsRes, positionsRes] = await Promise.all([
        engineClient.getExecutionFills({ symbol, limit: 200 }).catch(() => null),
        engineClient.getPositions().catch(() => null),
      ]);

      // Convert fills to execution markers
      if (fillsRes) {
        const mapped: Execution[] = fillsRes.fills.map((fill: ExecutionFill) => ({
          ts: fill.ts,
          type: fill.is_close ? "EXIT" as const : "ENTRY" as const,
          direction: fill.direction,
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
            if (pos.sl_price) {
              levels.push({
                type: "SL",
                price: pos.sl_price,
                direction: pos.direction,
                symbol: pos.symbol,
              });
            }
            if (pos.tp_price) {
              levels.push({
                type: "TP",
                price: pos.tp_price,
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
