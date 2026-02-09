/**
 * Hook for managing market data subscriptions.
 */

import { useCallback, useState } from "react";
import { engineClient, SubscribeResponse } from "../lib/engineClient";

interface UseMarketSubscriptionResult {
  subscribe: (
    symbols: string[],
    mode?: "stream" | "poll"
  ) => Promise<SubscribeResponse>;
  unsubscribe: (symbols: string[]) => Promise<void>;
  unsubscribeAll: () => Promise<void>;
  isSubscribing: boolean;
  lastError: string | null;
}

export function useMarketSubscription(): UseMarketSubscriptionResult {
  const [isSubscribing, setIsSubscribing] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  const subscribe = useCallback(
    async (
      symbols: string[],
      mode: "stream" | "poll" = "stream"
    ): Promise<SubscribeResponse> => {
      setIsSubscribing(true);
      setLastError(null);
      try {
        const response = await engineClient.subscribe({ symbols, mode });
        if (!response.ok) {
          setLastError(response.message);
        }
        return response;
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Subscription failed";
        setLastError(msg);
        throw e;
      } finally {
        setIsSubscribing(false);
      }
    },
    []
  );

  const unsubscribe = useCallback(async (symbols: string[]) => {
    try {
      await engineClient.unsubscribe({ symbols });
    } catch (e) {
      setLastError(e instanceof Error ? e.message : "Unsubscribe failed");
    }
  }, []);

  const unsubscribeAll = useCallback(async () => {
    try {
      await engineClient.unsubscribe({ symbols: [] });
    } catch (e) {
      setLastError(e instanceof Error ? e.message : "Unsubscribe all failed");
    }
  }, []);

  return {
    subscribe,
    unsubscribe,
    unsubscribeAll,
    isSubscribing,
    lastError,
  };
}
