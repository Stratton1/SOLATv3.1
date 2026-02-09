/**
 * Hook to fetch open positions from the execution engine.
 */

import { useState, useEffect, useCallback } from "react";
import { engineClient, OpenPosition } from "../lib/engineClient";

interface UsePositionsResult {
  positions: OpenPosition[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export function usePositions(): UsePositionsResult {
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPositions = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await engineClient.getPositions();
      setPositions(res.positions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch positions");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPositions();
  }, [fetchPositions]);

  // Poll every 10s
  useEffect(() => {
    const interval = setInterval(fetchPositions, 10000);
    return () => clearInterval(interval);
  }, [fetchPositions]);

  return { positions, isLoading, error, refresh: fetchPositions };
}
