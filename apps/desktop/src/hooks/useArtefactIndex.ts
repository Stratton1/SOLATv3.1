/**
 * Hook for fetching the artefact index from the engine.
 */

import { useState, useEffect, useCallback } from "react";
import { engineClient } from "../lib/engineClient";

export interface BarSummary {
  symbol: string;
  timeframe: string;
  row_count: number;
  start_ts?: string;
  end_ts?: string;
}

export interface BacktestSummary {
  run_id: string;
  created_at?: string;
  symbols?: string[];
  bots?: string[];
  timeframe?: string;
  sharpe?: number;
  total_trades?: number;
  path?: string;
}

export interface SweepSummary {
  sweep_id: string;
  scope?: string;
  total_combos?: number;
  top_sharpe?: number;
  generated_at?: string;
  path?: string;
}

export interface ArtefactIndex {
  bars: BarSummary[];
  backtests: BacktestSummary[];
  sweeps: SweepSummary[];
  generated_at: string;
}

interface UseArtefactIndexResult {
  data: ArtefactIndex | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useArtefactIndex(): UseArtefactIndexResult {
  const [data, setData] = useState<ArtefactIndex | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const result = await engineClient.getArtefactIndex();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch artefact index");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, isLoading, error, refetch: fetchData };
}
