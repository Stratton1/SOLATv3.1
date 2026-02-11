/**
 * Hook for starting/stopping the Python engine via Tauri commands.
 * Also provides engine status polling and log retrieval.
 */

import { useCallback, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

export interface EngineStatus {
  running: boolean;
  pid: number | null;
  health_ok: boolean;
  health_body: string | null;
  health_error: string | null;
  log_tail: string;
  log_path: string;
}

interface UseEngineLauncherResult {
  startEngine: () => Promise<void>;
  stopEngine: () => Promise<void>;
  getEngineStatus: () => Promise<EngineStatus>;
  getEngineLog: () => Promise<string>;
  isStarting: boolean;
  lastMessage: string | null;
  lastError: string | null;
}

export function useEngineLauncher(): UseEngineLauncherResult {
  const [isStarting, setIsStarting] = useState(false);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const startEngine = useCallback(async () => {
    setIsStarting(true);
    setLastError(null);
    try {
      const msg = await invoke<string>("start_engine");
      setLastMessage(msg);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLastError(message);
    } finally {
      setIsStarting(false);
    }
  }, []);

  const stopEngine = useCallback(async () => {
    try {
      const msg = await invoke<string>("stop_engine");
      setLastMessage(msg);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLastError(message);
    }
  }, []);

  const getEngineStatus = useCallback(async (): Promise<EngineStatus> => {
    return invoke<EngineStatus>("get_engine_status");
  }, []);

  const getEngineLog = useCallback(async (): Promise<string> => {
    return invoke<string>("get_engine_log");
  }, []);

  return {
    startEngine,
    stopEngine,
    getEngineStatus,
    getEngineLog,
    isStarting,
    lastMessage,
    lastError,
  };
}
