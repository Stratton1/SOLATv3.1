/**
 * Hook for LIVE trading gates.
 *
 * Provides state and actions for:
 * - Fetching gate status
 * - Running prelive check
 * - Confirming LIVE mode
 * - Revoking LIVE confirmation
 */

import { useState, useCallback, useEffect } from "react";
import {
  engineClient,
  GateStatus,
  PreliveCheckResult,
  LiveConfirmResponse,
} from "../lib/engineClient";

interface UseLiveGatesState {
  gates: GateStatus | null;
  preliveResult: PreliveCheckResult | null;
  loading: boolean;
  error: string | null;
  isLiveAllowed: boolean;
  isLiveMode: boolean;
  blockers: string[];
  warnings: string[];
}

interface UseLiveGatesActions {
  refreshGates: () => Promise<void>;
  runPreliveCheck: () => Promise<PreliveCheckResult | null>;
  confirmLive: (
    phrase: string,
    token: string,
    accountId: string
  ) => Promise<LiveConfirmResponse | null>;
  revokeLive: () => Promise<boolean>;
}

export function useLiveGates(
  autoRefresh: boolean = false,
  refreshInterval: number = 10000
): UseLiveGatesState & UseLiveGatesActions {
  const [gates, setGates] = useState<GateStatus | null>(null);
  const [preliveResult, setPreliveResult] = useState<PreliveCheckResult | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshGates = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await engineClient.getGates();
      setGates(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch gates");
    } finally {
      setLoading(false);
    }
  }, []);

  const runPreliveCheck = useCallback(async (): Promise<PreliveCheckResult | null> => {
    try {
      setLoading(true);
      setError(null);
      const result = await engineClient.runPreliveCheck();
      setPreliveResult(result);
      // Refresh gates after prelive check
      await refreshGates();
      return result;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to run prelive check"
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, [refreshGates]);

  const confirmLive = useCallback(
    async (
      phrase: string,
      token: string,
      accountId: string
    ): Promise<LiveConfirmResponse | null> => {
      try {
        setLoading(true);
        setError(null);
        const result = await engineClient.confirmLive({
          phrase,
          token,
          account_id: accountId,
        });
        // Refresh gates after confirmation
        await refreshGates();
        return result;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to confirm LIVE mode"
        );
        return null;
      } finally {
        setLoading(false);
      }
    },
    [refreshGates]
  );

  const revokeLive = useCallback(async (): Promise<boolean> => {
    try {
      setLoading(true);
      setError(null);
      await engineClient.revokeLive();
      // Refresh gates after revoke
      await refreshGates();
      return true;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to revoke LIVE confirmation"
      );
      return false;
    } finally {
      setLoading(false);
    }
  }, [refreshGates]);

  // Initial fetch
  useEffect(() => {
    refreshGates();
  }, [refreshGates]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(refreshGates, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, refreshGates]);

  return {
    gates,
    preliveResult,
    loading,
    error,
    isLiveAllowed: gates?.allowed ?? false,
    isLiveMode: gates?.mode === "LIVE",
    blockers: gates?.blockers ?? [],
    warnings: gates?.warnings ?? [],
    refreshGates,
    runPreliveCheck,
    confirmLive,
    revokeLive,
  };
}

/**
 * Required phrase for LIVE confirmation.
 */
export const LIVE_CONFIRM_PHRASE = "ENABLE LIVE TRADING";

/**
 * Validate the confirmation phrase.
 */
export function validatePhrase(input: string): boolean {
  return input.trim().toUpperCase() === LIVE_CONFIRM_PHRASE;
}
