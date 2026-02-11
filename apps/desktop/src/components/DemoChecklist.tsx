/**
 * DEMO Test Checklist — 5-step setup guide for DEMO trading.
 *
 * Steps:
 * 1. Connect IG DEMO
 * 2. Enable Signals
 * 3. Set Allowlist
 * 4. Arm DEMO
 * 5. Run Once (manual)
 */

import { useState, useEffect } from "react";
import { useExecutionStatus } from "../hooks/useExecutionStatus";
import { useExecutionMode } from "../hooks/useExecutionMode";
import { engineClient } from "../lib/engineClient";
import { InfoTip } from "./InfoTip";

interface ChecklistStep {
  label: string;
  description: string;
  status: "pending" | "done" | "manual";
}

export function DemoChecklist() {
  const { status: execStatus } = useExecutionStatus();
  const { mode: execMode } = useExecutionMode();
  const [allowlistCount, setAllowlistCount] = useState<number | null>(null);

  useEffect(() => {
    engineClient
      .getAllowlist()
      .then((res) => setAllowlistCount(res.count))
      .catch(() => setAllowlistCount(0));
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
      description: "Manually trigger a strategy cycle via Autopilot > Run Once.",
      status: "manual",
    },
  ];

  const completedCount = steps.filter((s) => s.status === "done").length;

  return (
    <div className="demo-checklist">
      <div className="card-header">
        <span className="card-title">
          DEMO Setup
          <InfoTip text="Complete these steps to run your first DEMO trade. Steps 1-4 are auto-checked. Step 5 is manual." />
        </span>
        <span className="card-badge demo">
          {completedCount}/4 complete
        </span>
      </div>
      <ul className="checklist-steps">
        {steps.map((step) => (
          <li
            key={step.label}
            className={`checklist-step ${step.status}`}
          >
            <span className="checklist-icon">
              {step.status === "done"
                ? "\u2713"
                : step.status === "manual"
                  ? "\u2022"
                  : "\u25CB"}
            </span>
            <div className="checklist-content">
              <span className="checklist-label">{step.label}</span>
              <span className="checklist-desc">{step.description}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
