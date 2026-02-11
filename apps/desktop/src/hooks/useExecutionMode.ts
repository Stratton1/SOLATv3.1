/**
 * Hook for execution mode flags (signals_enabled, demo_arm_enabled).
 */

import { useState, useEffect, useCallback } from "react";
import { engineClient, ExecutionModeFlags } from "../lib/engineClient";

interface UseExecutionModeResult {
  mode: ExecutionModeFlags | null;
  isLoading: boolean;
  error: string | null;
  setSignalsEnabled: (enabled: boolean) => Promise<void>;
  setDemoArmEnabled: (enabled: boolean) => Promise<void>;
  refetch: () => void;
}

export function useExecutionMode(): UseExecutionModeResult {
  const [mode, setMode] = useState<ExecutionModeFlags | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await engineClient.getExecutionMode();
      setMode(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch execution mode");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const setSignalsEnabled = useCallback(
    async (enabled: boolean) => {
      try {
        setError(null);
        const result = await engineClient.setExecutionMode({ signals_enabled: enabled });
        setMode({
          signals_enabled: result.signals_enabled,
          demo_arm_enabled: result.demo_arm_enabled,
          mode: result.mode,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update signals_enabled");
      }
    },
    []
  );

  const setDemoArmEnabled = useCallback(
    async (enabled: boolean) => {
      try {
        setError(null);
        const result = await engineClient.setExecutionMode({ demo_arm_enabled: enabled });
        setMode({
          signals_enabled: result.signals_enabled,
          demo_arm_enabled: result.demo_arm_enabled,
          mode: result.mode,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update demo_arm_enabled");
      }
    },
    []
  );

  return {
    mode,
    isLoading,
    error,
    setSignalsEnabled,
    setDemoArmEnabled,
    refetch: fetchData,
  };
}
