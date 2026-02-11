/**
 * Backtest Wizard — 3-step modal for configuring and running a backtest.
 *
 * Steps:
 * 1. Select bots from Elite 8
 * 2. Select symbols + timeframe + date range
 * 3. Review summary + run
 */

import { useState, useCallback, useMemo } from "react";
import { ELITE_8_BOTS, CATEGORIES } from "../../lib/elite8Meta";
import { TIMEFRAMES } from "../../lib/workspace";
import { BacktestRequest } from "../../lib/engineClient";
import { useBacktestRunner } from "../../hooks/useBacktestRunner";

interface BacktestWizardProps {
  onClose: () => void;
  onComplete: (runId: string) => void;
}

const SEED_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"];

type Step = 1 | 2 | 3;

export function BacktestWizard({ onClose, onComplete }: BacktestWizardProps) {
  const [step, setStep] = useState<Step>(1);

  // Step 1: Bot selection
  const [selectedBots, setSelectedBots] = useState<Set<string>>(new Set());

  // Step 2: Symbol + TF + dates
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(
    new Set(["EURUSD"])
  );
  const [selectedTimeframe, setSelectedTimeframe] = useState("1h");
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return d.toISOString().split("T")[0];
  });
  const [endDate, setEndDate] = useState(() => {
    return new Date().toISOString().split("T")[0];
  });

  // Runner
  const { runId, status, isRunning, error, startBacktest, reset } =
    useBacktestRunner();

  const toggleBot = useCallback((id: string) => {
    setSelectedBots((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSymbol = useCallback((symbol: string) => {
    setSelectedSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });
  }, []);

  const canProceed = useMemo(() => {
    if (step === 1) return selectedBots.size > 0;
    if (step === 2) return selectedSymbols.size > 0 && startDate && endDate;
    return true;
  }, [step, selectedBots.size, selectedSymbols.size, startDate, endDate]);

  const handleRun = useCallback(async () => {
    const request: BacktestRequest = {
      symbols: Array.from(selectedSymbols),
      bots: Array.from(selectedBots),
      timeframe: selectedTimeframe,
      start_date: startDate,
      end_date: endDate,
    };
    await startBacktest(request);
  }, [selectedSymbols, selectedBots, selectedTimeframe, startDate, endDate, startBacktest]);

  // Auto-navigate when done
  if (status?.status === "done" && runId) {
    onComplete(runId);
    return null;
  }

  return (
    <div className="wizard-backdrop" onClick={onClose}>
      <div className="wizard-container" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="wizard-header">
          <h3>New Backtest</h3>
          <button className="wizard-close-btn" onClick={onClose}>
            {"\u2715"}
          </button>
        </div>

        {/* Stepper */}
        <div className="wizard-stepper">
          <div className={`wizard-step ${step === 1 ? "active" : step > 1 ? "completed" : ""}`}>
            <span className="wizard-step-number">{step > 1 ? "\u2713" : "1"}</span>
            <span>Select Bots</span>
          </div>
          <div className={`wizard-step ${step === 2 ? "active" : step > 2 ? "completed" : ""}`}>
            <span className="wizard-step-number">{step > 2 ? "\u2713" : "2"}</span>
            <span>Symbols & Range</span>
          </div>
          <div className={`wizard-step ${step === 3 ? "active" : ""}`}>
            <span className="wizard-step-number">3</span>
            <span>Review & Run</span>
          </div>
        </div>

        {/* Body */}
        <div className="wizard-body">
          {isRunning ? (
            <div className="wizard-running">
              <div className="loading-spinner" />
              <p>{status?.message || "Running backtest..."}</p>
              {status?.progress != null && (
                <p className="num" style={{ marginTop: 8, color: "var(--text-muted)" }}>
                  Progress: {Math.round(status.progress * 100)}%
                </p>
              )}
            </div>
          ) : status?.status === "failed" ? (
            <div className="wizard-running">
              <div style={{ marginBottom: "1rem" }}>
                <p style={{ color: "var(--accent-red)", fontWeight: 600, marginBottom: "0.5rem" }}>
                  Backtest Failed
                </p>
                {status.error_type && (
                  <p style={{ fontSize: "0.9em", color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
                    Error type: {status.error_type}
                  </p>
                )}
                <p style={{ fontSize: "0.9em", color: "var(--text-primary)" }}>
                  {status.error_message || status.message || "Unknown error"}
                </p>
              </div>
              <button
                className="wizard-btn"
                onClick={() => {
                  reset();
                  setStep(1);
                }}
              >
                Try Again
              </button>
            </div>
          ) : error ? (
            <div className="wizard-running">
              <p style={{ color: "var(--accent-red)", marginBottom: "1rem" }}>{error}</p>
              <button
                className="wizard-btn"
                onClick={() => {
                  reset();
                  setStep(1);
                }}
              >
                Try Again
              </button>
            </div>
          ) : step === 1 ? (
            <div className="wizard-bot-list">
              {ELITE_8_BOTS.map((bot) => (
                <div
                  key={bot.id}
                  className={`wizard-bot-item ${selectedBots.has(bot.id) ? "selected" : ""}`}
                  onClick={() => toggleBot(bot.id)}
                >
                  <input
                    type="checkbox"
                    checked={selectedBots.has(bot.id)}
                    onChange={() => toggleBot(bot.id)}
                  />
                  <div>
                    <div className="wizard-bot-name">{bot.name}</div>
                    <div className="wizard-bot-category">
                      {CATEGORIES[bot.category].label}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : step === 2 ? (
            <>
              <div className="wizard-field">
                <label>Symbols</label>
                <div className="wizard-tf-chips">
                  {SEED_SYMBOLS.map((sym) => (
                    <button
                      key={sym}
                      className={`wizard-tf-chip ${selectedSymbols.has(sym) ? "selected" : ""}`}
                      onClick={() => toggleSymbol(sym)}
                    >
                      {sym}
                    </button>
                  ))}
                </div>
              </div>
              <div className="wizard-field">
                <label>Timeframe</label>
                <div className="wizard-tf-chips">
                  {TIMEFRAMES.map((tf) => (
                    <button
                      key={tf}
                      className={`wizard-tf-chip ${selectedTimeframe === tf ? "selected" : ""}`}
                      onClick={() => setSelectedTimeframe(tf)}
                    >
                      {tf}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                <div className="wizard-field" style={{ flex: 1 }}>
                  <label>Start Date</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                  />
                </div>
                <div className="wizard-field" style={{ flex: 1 }}>
                  <label>End Date</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                  />
                </div>
              </div>
            </>
          ) : (
            <dl className="wizard-summary">
              <dt>Bots</dt>
              <dd>
                {Array.from(selectedBots)
                  .map((id) => ELITE_8_BOTS.find((b) => b.id === id)?.name ?? id)
                  .join(", ")}
              </dd>
              <dt>Symbols</dt>
              <dd>{Array.from(selectedSymbols).join(", ")}</dd>
              <dt>Timeframe</dt>
              <dd>{selectedTimeframe}</dd>
              <dt>Date Range</dt>
              <dd>
                {startDate} to {endDate}
              </dd>
            </dl>
          )}
        </div>

        {/* Footer */}
        {!isRunning && !error && status?.status !== "failed" && (
          <div className="wizard-footer">
            <button
              className="wizard-btn"
              onClick={step > 1 ? () => setStep((s) => (s - 1) as Step) : onClose}
            >
              {step > 1 ? "Back" : "Cancel"}
            </button>
            {step < 3 ? (
              <button
                className="wizard-btn primary"
                disabled={!canProceed}
                onClick={() => setStep((s) => (s + 1) as Step)}
              >
                Next
              </button>
            ) : (
              <button
                className="wizard-btn primary"
                onClick={handleRun}
              >
                Run Backtest
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
