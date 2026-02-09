/**
 * Hook for managing instrument catalogue data.
 */

import { useCallback, useEffect, useState } from "react";
import { CatalogueItem, engineClient } from "../lib/engineClient";

interface UseCatalogueResult {
  items: CatalogueItem[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
  getBySymbol: (symbol: string) => CatalogueItem | undefined;
  enrichedItems: CatalogueItem[];
}

export function useCatalogue(): UseCatalogueResult {
  const [items, setItems] = useState<CatalogueItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await engineClient.getCatalogue();
      setItems(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load catalogue");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const getBySymbol = useCallback(
    (symbol: string) => items.find((item) => item.symbol === symbol),
    [items]
  );

  const enrichedItems = items.filter((item) => item.epic);

  return {
    items,
    isLoading,
    error,
    refetch: fetch,
    getBySymbol,
    enrichedItems,
  };
}
