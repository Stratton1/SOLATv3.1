/**
 * Hook for fetching and managing recommendation sets.
 */

import { useState, useEffect, useCallback } from "react";
import {
  engineClient,
  RecommendedSet,
  RecommendedSetSummary,
  GenerateRecommendationsParams,
} from "../lib/engineClient";

interface UseRecommendationsResult {
  latest: RecommendedSet | null;
  all: RecommendedSetSummary[];
  isLoading: boolean;
  error: string | null;
  generate: (params: GenerateRecommendationsParams) => Promise<RecommendedSet | null>;
  applyDemo: (id: string) => Promise<void>;
  refetch: () => void;
}

export function useRecommendations(): UseRecommendationsResult {
  const [latest, setLatest] = useState<RecommendedSet | null>(null);
  const [all, setAll] = useState<RecommendedSetSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const allRes = await engineClient.listRecommendations();
      setAll(allRes);

      // Avoid /latest 404 noise when no recommendation sets exist.
      if (allRes.length === 0) {
        setLatest(null);
      } else {
        setLatest(await engineClient.getRecommendation(allRes[0].id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch recommendations");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const generate = useCallback(
    async (params: GenerateRecommendationsParams): Promise<RecommendedSet | null> => {
      try {
        const result = await engineClient.generateRecommendations(params);
        await fetchData();
        return result;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to generate recommendations");
        return null;
      }
    },
    [fetchData]
  );

  const applyDemo = useCallback(
    async (id: string) => {
      try {
        await engineClient.applyRecommendationDemo(id);
        await fetchData();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to apply recommendation");
      }
    },
    [fetchData]
  );

  return {
    latest,
    all,
    isLoading,
    error,
    generate,
    applyDemo,
    refetch: fetchData,
  };
}
