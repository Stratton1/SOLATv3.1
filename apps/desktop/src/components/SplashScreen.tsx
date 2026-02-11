/**
 * Animated splash/boot screen shown during engine startup.
 *
 * Uses raw fetch() for health checks (works immediately, no IPC dependency).
 * Supplements with Tauri invoke for process-level diagnostics on failure.
 *
 * Boot flow:
 *  1. Shell init (instant)
 *  2. Poll /health every 1s for up to 15s
 *  3. If healthy: warm catalogue, then transition to app
 *  4. If timeout/dead: show error with logs, retry, diagnostics
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-shell";
import { engineClient } from "../lib/engineClient";

const BOOT_TIMEOUT_MS = 15_000;
const POLL_MS = 1_000;
const ENGINE_URL = "http://127.0.0.1:8765";
const MIN_SPLASH_MS = 8_000; // Match video duration — always play full animation

type BootStage = "shell" | "engine" | "catalogue" | "ready" | "failed";

const STAGE_LABELS: Record<BootStage, string> = {
  shell: "Initialising desktop shell\u2026",
  engine: "Starting engine\u2026",
  catalogue: "Loading catalogue & scheduler\u2026",
  ready: "Ready",
  failed: "Engine not reachable",
};

interface SplashScreenProps {
  onReady: () => void;
  onStartEngine?: () => void;
}

export function SplashScreen({ onReady, onStartEngine }: SplashScreenProps) {
  const [stage, setStage] = useState<BootStage>("shell");
  const [progress, setProgress] = useState(0);
  const [fading, setFading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [logTail, setLogTail] = useState<string | null>(null);
  const [logPath, setLogPath] = useState<string | null>(null);
  const [diagnosticsJson, setDiagnosticsJson] = useState<string | null>(null);
  const [copyLabel, setCopyLabel] = useState("Copy Diagnostics");

  // Version counter: incremented on cleanup/retry to cancel stale boot sequences.
  // Survives React StrictMode double-mount because the ref persists across renders.
  const bootVersionRef = useRef(0);

  const tryBoot = useCallback(async () => {
    const myVersion = ++bootVersionRef.current;
    const isStale = () => bootVersionRef.current !== myVersion;
    const bootStart = Date.now();

    // Reset
    setErrorMsg(null);
    setLogTail(null);
    setDiagnosticsJson(null);
    setCopyLabel("Copy Diagnostics");

    // Stage 1: shell (instant)
    setStage("shell");
    setProgress(10);
    await sleep(300);
    if (isStale()) return;

    // Stage 2: poll /health via fetch
    setStage("engine");
    setProgress(20);

    const deadline = Date.now() + BOOT_TIMEOUT_MS;
    let healthy = false;

    while (Date.now() < deadline && !isStale()) {
      try {
        const res = await fetch(`${ENGINE_URL}/health`, {
          signal: AbortSignal.timeout(2000),
        });
        if (res.ok) {
          const body = await res.text();
          if (body.includes("healthy")) {
            healthy = true;
            break;
          }
        }
      } catch {
        // Engine not ready yet — expected during startup
      }

      // Check if engine process died (via Tauri command)
      try {
        const status = await invoke<{
          running: boolean;
          pid: number | null;
          log_tail: string;
          log_path: string;
        }>("get_engine_status");

        // Process exited and we have a pid (was tracked) — immediate failure
        if (!status.running && status.pid !== null) {
          if (isStale()) return;
          setStage("failed");
          setErrorMsg(`Engine process (pid ${status.pid}) exited unexpectedly.`);
          setLogTail(status.log_tail || null);
          setLogPath(status.log_path || null);
          setDiagnosticsJson(JSON.stringify(status, null, 2));
          return;
        }

        if (status.log_path) setLogPath(status.log_path);
      } catch {
        // Tauri IPC not ready yet — ignore
      }

      await sleep(POLL_MS);
      if (!isStale()) {
        setProgress((prev) => Math.min(prev + 2, 50));
      }
    }

    if (isStale()) return;

    if (!healthy) {
      // Timeout — gather diagnostics
      setStage("failed");
      let errText = `Engine not healthy after ${BOOT_TIMEOUT_MS / 1000}s.`;
      try {
        const status = await invoke<{
          running: boolean;
          pid: number | null;
          health_error: string | null;
          log_tail: string;
          log_path: string;
        }>("get_engine_status");
        if (status.health_error) errText += ` ${status.health_error}`;
        setLogTail(status.log_tail || null);
        setLogPath(status.log_path || null);
        setDiagnosticsJson(JSON.stringify(status, null, 2));
      } catch {
        // no diagnostics available
      }
      setErrorMsg(errText);
      return;
    }

    // Stage 3: warm catalogue + scheduler
    setProgress(60);
    setStage("catalogue");

    try {
      await Promise.allSettled([
        engineClient.getCatalogue(),
        engineClient.getSchedulerStatus(),
        engineClient.getHealth(),
        engineClient.getConfig(),
      ]);
    } catch {
      // Non-fatal
    }

    if (isStale()) return;
    setProgress(100);
    setStage("ready");

    // Wait for the full splash animation to finish before transitioning
    const elapsed = Date.now() - bootStart;
    const remaining = MIN_SPLASH_MS - elapsed;
    if (remaining > 0) {
      await sleep(remaining);
    }

    if (isStale()) return;

    // Fade out before transitioning
    setFading(true);
    await sleep(600);

    if (!isStale()) {
      onReady();
    }
  }, [onReady]);

  const handleRetry = useCallback(() => {
    setProgress(0);
    tryBoot();
  }, [tryBoot]);

  const handleRetryWithStart = useCallback(() => {
    onStartEngine?.();
    setTimeout(handleRetry, 2000);
  }, [onStartEngine, handleRetry]);

  const handleViewLogs = useCallback(async () => {
    if (!logPath) return;
    try {
      await open(logPath);
    } catch {
      try {
        const log = await invoke<string>("get_engine_log");
        setLogTail(log);
      } catch {
        // ignore
      }
    }
  }, [logPath]);

  const handleCopyDiagnostics = useCallback(() => {
    if (!diagnosticsJson) return;
    navigator.clipboard.writeText(diagnosticsJson).then(() => {
      setCopyLabel("Copied!");
      setTimeout(() => setCopyLabel("Copy Diagnostics"), 2000);
    });
  }, [diagnosticsJson]);

  useEffect(() => {
    tryBoot();
    return () => {
      // Invalidate the running boot sequence so it stops at next isStale() check
      bootVersionRef.current++;
    };
  }, [tryBoot]);

  const isFailed = stage === "failed";

  return (
    <div className={`splash-screen${fading ? " splash-fade-out" : ""}`}>
      {!isFailed && (
        <>
          <video
            className="splash-video"
            src="/splash_animation.mp4"
            autoPlay
            muted
            playsInline
            loop={stage !== "ready"}
          />

          <div className="splash-bottom">
            <div className="splash-progress-area">
              <div className="splash-progress-track">
                <div
                  className="splash-progress-fill"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
            <p className="splash-brand">
              SOLAT<span className="splash-version">v3.1</span>
            </p>
            <p className="splash-stage-text">{STAGE_LABELS[stage]}</p>
          </div>
        </>
      )}

      {isFailed && (
        <div className="splash-failed">
          <div className="splash-logo">
            <img src="/image_logo.png" alt="SOLAT" className="splash-logo-img" />
          </div>
          <p className="splash-failed-title">Engine Not Reachable</p>
          <p className="splash-failed-msg">
            {errorMsg ?? "The SOLAT engine did not respond in time."}
          </p>

          {logTail && <pre className="splash-log-tail">{logTail}</pre>}

          <div className="splash-failed-actions">
            {onStartEngine && (
              <button
                className="splash-btn splash-btn-primary"
                onClick={handleRetryWithStart}
              >
                Start Engine &amp; Retry
              </button>
            )}
            <button
              className="splash-btn splash-btn-secondary"
              onClick={handleRetry}
            >
              Retry Connection
            </button>
            {logPath && (
              <button
                className="splash-btn splash-btn-secondary"
                onClick={handleViewLogs}
              >
                View Logs
              </button>
            )}
            {diagnosticsJson && (
              <button
                className="splash-btn splash-btn-secondary"
                onClick={handleCopyDiagnostics}
              >
                {copyLabel}
              </button>
            )}
            <button
              className="splash-btn splash-btn-ghost"
              onClick={() => {
                bootVersionRef.current++;
                onReady();
              }}
            >
              Skip to App
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
