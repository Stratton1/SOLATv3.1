/**
 * DEMO Test Checklist — 5-step setup guide for DEMO trading.
 *
 * Steps:
 * 1. Connect IG DEMO
 * 2. Enable Signals
 * 3. Set Allowlist
 * 4. Arm DEMO
 * 5. Run Once
 */

import { useState, useEffect, useCallback } from "react";
import { useExecutionStatus } from "../hooks/useExecutionStatus";
import { useExecutionMode } from "../hooks/useExecutionMode";
import { engineClient } from "../lib/engineClient";
import { InfoTip } from "./InfoTip";

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

export function DemoChecklist() {
  const { status: execStatus } = useExecutionStatus();
  const { mode: execMode } = useExecutionMode();
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
    } catch (err) {
      setRunOnceResult({
        ok: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setRunOnceLoading(false);
    }
  }, []);

  const steps: ChecklistStep[] = [
    {
      label: "1. Connect IG DEMO",
      description: "Connect to your IG DEMO account via Execution Control.",
      status: execStatus?.connected ? "done" : "pending",
    },
    {
      label: "2. Enable Signals",
      description: "Turn on signal generation in the execution engine.",
      status: execMode?.signals_enabled ? "done" : "pending",
    },
    {
      label: "3. Set Allowlist",
      description: "Add at least one bot/symbol combo to the allowlist.",
      status:
        allowlistCount !== null && allowlistCount > 0 ? "done" : "pending",
    },
    {
      label: "4. Arm DEMO",
      description: "Arm the execution engine for DEMO order routing.",
      status: execStatus?.armed ? "done" : "pending",
    },
    {
      label: "5. Run Once",
      description: "Send a test order through the full execution pipeline.",
      status: runOnceDone ? "done" : stepsReady ? "manual" : "pending",
    },
  ];

  const completedCount = steps.filter((s) => s.status === "done").length;

  return (
    <div className="demo-checklist">
      <div className="card-header">
        <span className="card-title">
          DEMO Setup
          <InfoTip text="Complete these steps to run your first DEMO trade. Steps 1-4 are auto-checked. Step 5 sends a test order." />
        </span>
        <span className="card-badge demo">
          {completedCount}/5 complete
        </span>
      </div>
      <ul className="checklist-steps">
        {steps.map((step, idx) => (
          <li
            key={step.label}
            className={`checklist-step ${step.status}`}
          >
            <span className="checklist-icon">
              {step.status === "done"
                ? "\u2713"
                : step.status === "manual"
                  ? "\u25CF"
                  : "\u25CB"}
            </span>
            <div className="checklist-content">
              <span className="checklist-label">{step.label}</span>
              <span className="checklist-desc">{step.description}</span>
              {idx === 4 && stepsReady && !runOnceDone && (
                <button
                  className="btn btn-sm btn-accent"
                  onClick={handleRunOnce}
                  disabled={runOnceLoading}
                  style={{ marginTop: 4 }}
                >
                  {runOnceLoading ? "Sending..." : "Run Once"}
                </button>
              )}
              {idx === 4 && runOnceResult && (
                <div
                  className={`checklist-result ${runOnceResult.ok ? "success" : "error"}`}
                  style={{ marginTop: 4, fontSize: "0.85em" }}
                >
                  {runOnceResult.ok ? (
                    <span>
                      {runOnceResult.status} | deal: {runOnceResult.deal_id ?? "n/a"}
                    </span>
                  ) : (
                    <span className="text-error">
                      {runOnceResult.error ?? "Failed"}
                    </span>
                  )}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
