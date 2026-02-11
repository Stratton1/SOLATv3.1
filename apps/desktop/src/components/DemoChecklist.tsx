/**
 * DEMO Test Checklist — 5-step setup guide for DEMO trading.
 */

import { useState, useEffect, useCallback } from "react";
import { useExecutionStatus } from "../hooks/useExecutionStatus";
import { useExecutionMode } from "../hooks/useExecutionMode";
import { engineClient } from "../lib/engineClient";
import { useToast } from "../context/ToastContext";

interface DemoChecklistProps {
  onScrollToConnect?: () => void;
}

interface ChecklistStep {
  label: string;
  description: string;
  status: "pending" | "done" | "manual";
}

interface RunOnceResult {
  ok: boolean;
  intent_id?: string;
  status?: string;
  deal_id?: string;
  error?: string;
}

export function DemoChecklist({ onScrollToConnect }: DemoChecklistProps) {
  const { status: execStatus } = useExecutionStatus();
  const { mode: execMode } = useExecutionMode();
  const { showToast } = useToast();
  const [allowlistCount, setAllowlistCount] = useState<number | null>(null);
  const [runOnceResult, setRunOnceResult] = useState<RunOnceResult | null>(null);
  const [runOnceLoading, setRunOnceLoading] = useState(false);

  useEffect(() => {
    engineClient
      .getAllowlist()
      .then((res) => setAllowlistCount(res.count))
      .catch(() => setAllowlistCount(0));
  }, []);

  const stepsReady =
    execStatus?.connected &&
    execMode?.signals_enabled &&
    allowlistCount !== null &&
    allowlistCount > 0 &&
    execStatus?.armed;

  const runOnceDone = runOnceResult?.ok === true;

  const handleRunOnce = useCallback(async () => {
    setRunOnceLoading(true);
    setRunOnceResult(null);
    try {
      const result = await engineClient.runOnce({
        symbol: "EURUSD",
        bot: "CloudTwist",
        side: "BUY",
        size: 0.1,
      });
      setRunOnceResult(result);
      if (result.ok) {
        showToast("Test order sent successfully", "success");
      } else {
        showToast(result.error || "Run Once failed", "error");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setRunOnceResult({ ok: false, error: msg });
      showToast(msg, "error");
    } finally {
      setRunOnceLoading(false);
    }
  }, [showToast]);

  const steps: ChecklistStep[] = [
    {
      label: "Connect IG DEMO",
      description: "Open a broker session via Execution Control.",
      status: execStatus?.connected ? "done" : "pending",
    },
    {
      label: "Enable Signals",
      description: "Toggle 'Signals Enabled' in Execution Control.",
      status: execMode?.signals_enabled ? "done" : "pending",
    },
    {
      label: "Set Allowlist",
      description: "Add bot/symbol combos via the Optimise tab.",
      status:
        allowlistCount !== null && allowlistCount > 0 ? "done" : "pending",
    },
    {
      label: "Arm DEMO",
      description: "Check 'DEMO Arm' then click ARM.",
      status: execStatus?.armed ? "done" : "pending",
    },
    {
      label: "Run Once",
      description: "Send a test order through the pipeline.",
      status: runOnceDone ? "done" : stepsReady ? "manual" : "pending",
    },
  ];

  const completedCount = steps.filter((s) => s.status === "done").length;

  return (
    <div className="demo-checklist-dense">
      <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 8, textAlign: "right" }}>
        {completedCount}/5 COMPLETE
      </div>
      <ul className="checklist-steps-dense">
        {steps.map((step, idx) => (
          <li
            key={step.label}
            className={`checklist-step-dense ${step.status}`}
          >
            <div className="checklist-dot" />
            <div className="checklist-content">
              <div className="checklist-header-row">
                <span className="checklist-label">{step.label}</span>
                {step.status === "done" && <span className="checklist-check">✓</span>}
              </div>
              <span className="checklist-desc">{step.description}</span>
              
              {/* Contextual Actions */}
              <div className="checklist-actions" style={{ marginTop: 4 }}>
                {idx === 0 && step.status === "pending" && onScrollToConnect && (
                  <button className="btn-inline" onClick={onScrollToConnect}>Go to Connect</button>
                )}
                {idx === 1 && step.status === "pending" && onScrollToConnect && (
                  <button className="btn-inline" onClick={onScrollToConnect}>Go to Execution Control</button>
                )}
                {idx === 2 && step.status === "pending" && (
                  <span className="checklist-hint">Configure in the Optimise tab</span>
                )}
                {idx === 3 && step.status === "pending" && execStatus?.connected && onScrollToConnect && (
                  <button className="btn-inline" onClick={onScrollToConnect}>Go to Execution Control</button>
                )}
                {idx === 4 && stepsReady && !runOnceDone && (
                  <button
                    className="wizard-btn primary sm"
                    onClick={handleRunOnce}
                    disabled={runOnceLoading}
                    style={{ fontSize: 10, padding: "2px 8px" }}
                  >
                    {runOnceLoading ? "Sending..." : "Trigger Run Once"}
                  </button>
                )}
              </div>

              {idx === 4 && runOnceResult && (
                <div className={`checklist-result ${runOnceResult.ok ? "text-green" : "text-red"}`} style={{ fontSize: 9, marginTop: 2 }}>
                  {runOnceResult.ok ? `SUCCESS: ${runOnceResult.status}` : `ERROR: ${runOnceResult.error}`}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
