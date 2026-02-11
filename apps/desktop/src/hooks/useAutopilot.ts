/**
 * Hook for autopilot state management.
 */

import { useState, useEffect, useCallback } from "react";
import { engineClient, AutopilotState } from "../lib/engineClient";

interface UseAutopilotResult {
  state: AutopilotState | null;
  isLoading: boolean;
  error: string | null;
  enable: () => Promise<void>;
  disable: () => Promise<void>;
  refetch: () => void;
}

const DEFAULT_STATE: AutopilotState = {
  enabled: false,
  enabled_at: null,
  combo_count: 0,
  cycle_count: 0,
  signals_generated: 0,
  intents_routed: 0,
  last_cycle_at: null,
  blocked_reasons: [],
};

export function useAutopilot(): UseAutopilotResult {
  const [state, setState] = useState<AutopilotState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const status = await engineClient.getAutopilotStatus();
      setState(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch autopilot status");
      setState(DEFAULT_STATE);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 5s when enabled
  useEffect(() => {
    if (!state?.enabled) return;
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [state?.enabled, fetchData]);

  const enable = useCallback(async () => {
    try {
      setError(null);
      await engineClient.enableAutopilot();
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enable autopilot");
    }
  }, [fetchData]);

  const disable = useCallback(async () => {
    try {
      setError(null);
      await engineClient.disableAutopilot();
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disable autopilot");
    }
  }, [fetchData]);

  return {
    state,
    isLoading,
    error,
    enable,
    disable,
    refetch: fetchData,
  };
}
