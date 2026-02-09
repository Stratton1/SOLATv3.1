import { useCallback, useEffect, useState } from "react";

const ENGINE_URL = "http://127.0.0.1:8765";

export interface ExecutionStatus {
  mode: string;
  connected: boolean;
  armed: boolean;
  kill_switch_active: boolean;
  account_id: string | null;
  account_balance: number | null;
  open_position_count: number;
  realized_pnl_today: number;
  trades_this_hour: number;
  last_error: string | null;
}

interface UseExecutionStatusResult {
  status: ExecutionStatus | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
  connect: () => Promise<{ ok: boolean; error?: string }>;
  disconnect: () => Promise<{ ok: boolean; error?: string }>;
  arm: (confirm: boolean) => Promise<{ ok: boolean; armed: boolean; error?: string }>;
  disarm: () => Promise<{ ok: boolean; armed: boolean }>;
  activateKillSwitch: (reason: string) => Promise<{ ok: boolean }>;
  resetKillSwitch: () => Promise<{ ok: boolean }>;
}

export function useExecutionStatus(): UseExecutionStatusResult {
  const [status, setStatus] = useState<ExecutionStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/execution/status`);
      if (!res.ok) {
        throw new Error("Failed to fetch execution status");
      }
      const data = await res.json();
      setStatus(data);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    // Poll every 2 seconds for execution status
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const connect = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/execution/connect`, {
        method: "POST",
      });
      const data = await res.json();
      if (res.ok) {
        await fetchStatus();
        return { ok: true };
      }
      return { ok: false, error: data.detail || "Connection failed" };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      return { ok: false, error: message };
    }
  }, [fetchStatus]);

  const disconnect = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/execution/disconnect`, {
        method: "POST",
      });
      if (res.ok) {
        await fetchStatus();
        return { ok: true };
      }
      const data = await res.json();
      return { ok: false, error: data.detail || "Disconnect failed" };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      return { ok: false, error: message };
    }
  }, [fetchStatus]);

  const arm = useCallback(
    async (confirm: boolean) => {
      try {
        const res = await fetch(`${ENGINE_URL}/execution/arm`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm }),
        });
        const data = await res.json();
        await fetchStatus();
        return { ok: data.ok, armed: data.armed, error: data.error };
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        return { ok: false, armed: false, error: message };
      }
    },
    [fetchStatus]
  );

  const disarm = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/execution/disarm`, {
        method: "POST",
      });
      const data = await res.json();
      await fetchStatus();
      return { ok: data.ok, armed: data.armed };
    } catch {
      return { ok: false, armed: false };
    }
  }, [fetchStatus]);

  const activateKillSwitch = useCallback(
    async (reason: string) => {
      try {
        const res = await fetch(`${ENGINE_URL}/execution/kill-switch/activate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason }),
        });
        const data = await res.json();
        await fetchStatus();
        return { ok: data.ok };
      } catch {
        return { ok: false };
      }
    },
    [fetchStatus]
  );

  const resetKillSwitch = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/execution/kill-switch/reset`, {
        method: "POST",
      });
      const data = await res.json();
      await fetchStatus();
      return { ok: data.ok };
    } catch {
      return { ok: false };
    }
  }, [fetchStatus]);

  return {
    status,
    isLoading,
    error,
    refetch: fetchStatus,
    connect,
    disconnect,
    arm,
    disarm,
    activateKillSwitch,
    resetKillSwitch,
  };
}
