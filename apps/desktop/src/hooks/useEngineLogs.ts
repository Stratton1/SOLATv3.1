import { useCallback, useEffect, useRef, useState } from "react";

const ENGINE_URL = "http://127.0.0.1:8765";
const POLL_INTERVAL_MS = 2000;

export interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  extra: Record<string, any>;
}

export interface LogsResponse {
  logs: LogEntry[];
}

export function useEngineLogs(level = "INFO", limit = 50) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/diagnostics/logs?level=${level}&limit=${limit}`);
      if (!res.ok) {
        throw new Error("Failed to fetch engine logs");
      }
      const data: LogsResponse = await res.json();
      setLogs(data.logs);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, [level, limit]);

  useEffect(() => {
    fetchLogs();
    pollIntervalRef.current = setInterval(fetchLogs, POLL_INTERVAL_MS);
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchLogs]);

  return { logs, isLoading, error, refetch: fetchLogs };
}
