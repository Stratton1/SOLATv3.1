/**
 * Hook for managing the asset allowlist.
 */

import { useState, useEffect, useCallback } from "react";
import { engineClient } from "../lib/engineClient";

interface UseAllowlistResult {
  allowlist: string[];
  isLoading: boolean;
  error: string | null;
  setAllowlist: (symbols: string[]) => Promise<void>;
  addSymbol: (symbol: string) => Promise<void>;
  removeSymbol: (symbol: string) => Promise<void>;
  refresh: () => void;
}

export function useAllowlist(): UseAllowlistResult {
  const [allowlist, setAllowlistState] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAllowlist = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await engineClient.getAllowlist();
      setAllowlistState(res.symbols);
    } catch (err) {
      // Allowlist endpoint may not exist yet; default to empty
      setError(err instanceof Error ? err.message : "Failed to fetch allowlist");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAllowlist();
  }, [fetchAllowlist]);

  const setAllowlist = useCallback(async (symbols: string[]) => {
    setError(null);
    try {
      const res = await engineClient.setAllowlist(symbols);
      setAllowlistState(res.symbols);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set allowlist");
      throw err;
    }
  }, []);

  const addSymbol = useCallback(
    async (symbol: string) => {
      if (allowlist.includes(symbol)) return;
      await setAllowlist([...allowlist, symbol]);
    },
    [allowlist, setAllowlist]
  );

  const removeSymbol = useCallback(
    async (symbol: string) => {
      await setAllowlist(allowlist.filter((s) => s !== symbol));
    },
    [allowlist, setAllowlist]
  );

  return {
    allowlist,
    isLoading,
    error,
    setAllowlist,
    addSymbol,
    removeSymbol,
    refresh: fetchAllowlist,
  };
}
