/**
 * Hook for fetching optimization scheduler status and proposals.
 */

import { useState, useEffect, useCallback } from "react";
import {
  engineClient,
  SchedulerStatus,
  Proposal,
} from "../lib/engineClient";

interface UseOptimizationResult {
  schedulerStatus: SchedulerStatus | null;
  proposals: Proposal[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
  applyProposal: (id: string) => Promise<void>;
}

export function useOptimization(): UseOptimizationResult {
  const [schedulerStatus, setSchedulerStatus] =
    useState<SchedulerStatus | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const [status, props] = await Promise.all([
        engineClient.getSchedulerStatus(),
        engineClient.listProposals(),
      ]);

      setSchedulerStatus(status);
      setProposals(props);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to fetch optimization data";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const applyProposal = useCallback(
    async (id: string) => {
      try {
        await engineClient.applyProposal(id);
        await fetchData(); // Refresh after applying
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to apply proposal";
        setError(message);
      }
    },
    [fetchData]
  );

  return {
    schedulerStatus,
    proposals,
    isLoading,
    error,
    refetch: fetchData,
    applyProposal,
  };
}
