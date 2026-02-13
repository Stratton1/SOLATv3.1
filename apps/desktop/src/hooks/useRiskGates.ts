import { useCallback, useEffect, useRef, useState } from "react";

const ENGINE_URL = "http://127.0.0.1:8765";
const POLL_INTERVAL_MS = 5000;

export interface GateStatusResponse {
  allowed: boolean;
  mode: string;
  blockers: string[];
  warnings: string[];
  details: Record<string, any>;
  confirmation_status: Record<string, any>;
  account_status: Record<string, any>;
}

export function useRiskGates() {
  const [data, setData] = useState<GateStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchGates = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/execution/gates`);
      if (!res.ok) {
        throw new Error("Failed to fetch risk gates");
      }
      const gatesData = await res.json();
      setData(gatesData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGates();
    pollIntervalRef.current = setInterval(fetchGates, POLL_INTERVAL_MS);
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchGates]);

  return { data, isLoading, error, refetch: fetchGates };
}
