/**
 * Hook for fetching terminal signals from the execution ledger.
 */

import { useState, useEffect, useCallback } from "react";
import { engineClient, TerminalSignal } from "../lib/engineClient";

interface UseTerminalSignalsResult {
  signals: TerminalSignal[];
  total: number;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useTerminalSignals(options?: {
  symbol?: string;
  bot?: string;
  limit?: number;
  autoRefreshMs?: number;
}): UseTerminalSignalsResult {
  const [signals, setSignals] = useState<TerminalSignal[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const limit = options?.limit ?? 50;
  const symbol = options?.symbol;
  const bot = options?.bot;
  const autoRefreshMs = options?.autoRefreshMs ?? 10000;

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await engineClient.getTerminalSignals({
        symbol,
        bot,
        limit,
      });
      setSignals(data.signals);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch signals");
    } finally {
      setIsLoading(false);
    }
  }, [symbol, bot, limit]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh
  useEffect(() => {
    if (autoRefreshMs <= 0) return;
    const interval = setInterval(fetchData, autoRefreshMs);
    return () => clearInterval(interval);
  }, [fetchData, autoRefreshMs]);

  return {
    signals,
    total,
    isLoading,
    error,
    refetch: fetchData,
  };
}
