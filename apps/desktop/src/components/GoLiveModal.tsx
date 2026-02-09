/**
 * GoLive Modal - Multi-step LIVE trading enable workflow.
 *
 * Steps:
 * 1. Warning acknowledgment
 * 2. Type confirmation phrase: "ENABLE LIVE TRADING"
 * 3. Paste LIVE_ENABLE_TOKEN from .env
 * 4. Run prelive check and verify PASS
 * 5. Confirm locked account ID
 * 6. Final confirmation
 *
 * SAFETY: This modal is intentionally hard to complete to prevent accidents.
 */

import { useState, useCallback, useEffect } from "react";
import {
  useLiveGates,
  LIVE_CONFIRM_PHRASE,
  validatePhrase,
} from "../hooks/useLiveGates";

interface GoLiveModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLiveEnabled: () => void;
  accountId: string;
}

type Step =
  | "warning"
  | "phrase"
  | "token"
  | "prelive"
  | "account"
  | "confirm"
  | "success";

export function GoLiveModal({
  isOpen,
  onClose,
  onLiveEnabled,
  accountId,
}: GoLiveModalProps) {
  const [step, setStep] = useState<Step>("warning");
  const [phraseInput, setPhraseInput] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [phraseValid, setPhraseValid] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [preliveRunning, setPreliveRunning] = useState(false);
  const [preliveError, setPreliveError] = useState<string | null>(null);

  const {
    gates,
    preliveResult,
    loading,
    error,
    runPreliveCheck,
    confirmLive,
  } = useLiveGates();

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setStep("warning");
      setPhraseInput("");
      setTokenInput("");
      setPhraseValid(false);
      setTokenError(null);
      setPreliveError(null);
    }
  }, [isOpen]);

  // Validate phrase as user types
  useEffect(() => {
    setPhraseValid(validatePhrase(phraseInput));
  }, [phraseInput]);

  const handlePhraseSubmit = useCallback(() => {
    if (phraseValid) {
      setStep("token");
    }
  }, [phraseValid]);

  const handleTokenSubmit = useCallback(() => {
    if (tokenInput.trim().length > 0) {
      setTokenError(null);
      setStep("prelive");
    }
  }, [tokenInput]);

  const handleRunPrelive = useCallback(async () => {
    setPreliveRunning(true);
    setPreliveError(null);

    try {
      const result = await runPreliveCheck();
      if (result?.passed) {
        setStep("account");
      } else {
        setPreliveError(
          `Prelive check failed: ${result?.blockers.join(", ") || "Unknown error"}`
        );
      }
    } catch (err) {
      setPreliveError(
        err instanceof Error ? err.message : "Prelive check failed"
      );
    } finally {
      setPreliveRunning(false);
    }
  }, [runPreliveCheck]);

  const handleConfirmAccount = useCallback(() => {
    setStep("confirm");
  }, []);

  const handleFinalConfirm = useCallback(async () => {
    try {
      const result = await confirmLive(
        LIVE_CONFIRM_PHRASE,
        tokenInput,
        accountId
      );

      if (result?.ok) {
        setStep("success");
        setTimeout(() => {
          onLiveEnabled();
          onClose();
        }, 2000);
      } else {
        setTokenError(result?.message || "LIVE confirmation failed");
        setStep("token");
      }
    } catch (err) {
      setTokenError(
        err instanceof Error ? err.message : "LIVE confirmation failed"
      );
      setStep("token");
    }
  }, [confirmLive, tokenInput, accountId, onLiveEnabled, onClose]);

  const handleBack = useCallback(() => {
    switch (step) {
      case "phrase":
        setStep("warning");
        break;
      case "token":
        setStep("phrase");
        break;
      case "prelive":
        setStep("token");
        break;
      case "account":
        setStep("prelive");
        break;
      case "confirm":
        setStep("account");
        break;
    }
  }, [step]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-zinc-900 border-2 border-red-600 rounded-lg shadow-2xl w-full max-w-lg p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-red-500 animate-pulse" />
            <h2 className="text-xl font-bold text-red-500">
              ENABLE LIVE TRADING
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        {/* Progress indicator */}
        <div className="flex gap-2 mb-6">
          {(["warning", "phrase", "token", "prelive", "account", "confirm"] as Step[]).map(
            (s, i) => (
              <div
                key={s}
                className={`h-1 flex-1 rounded ${
                  step === s
                    ? "bg-red-500"
                    : i <
                      ["warning", "phrase", "token", "prelive", "account", "confirm"].indexOf(
                        step
                      )
                    ? "bg-green-500"
                    : "bg-zinc-700"
                }`}
              />
            )
          )}
        </div>

        {/* Step: Warning */}
        {step === "warning" && (
          <div className="space-y-4">
            <div className="bg-red-900/30 border border-red-700 rounded p-4 text-red-200">
              <h3 className="font-bold text-lg mb-2">
                ⚠️ LIVE TRADING WARNING
              </h3>
              <ul className="list-disc list-inside space-y-1 text-sm">
                <li>You are about to enable REAL MONEY trading</li>
                <li>Orders will be placed with actual funds</li>
                <li>Financial losses are possible and irreversible</li>
                <li>This system is for personal use only</li>
                <li>
                  You accept full responsibility for any trading outcomes
                </li>
              </ul>
            </div>

            <div className="bg-zinc-800 rounded p-4 text-zinc-300 text-sm">
              <p>Current Mode: {gates?.mode || "DEMO"}</p>
              <p>Account ID: {accountId}</p>
            </div>

            <div className="flex justify-between">
              <button
                onClick={onClose}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded"
              >
                Cancel
              </button>
              <button
                onClick={() => setStep("phrase")}
                className="px-4 py-2 bg-red-700 hover:bg-red-600 rounded font-bold"
              >
                I Understand the Risks
              </button>
            </div>
          </div>
        )}

        {/* Step: Type phrase */}
        {step === "phrase" && (
          <div className="space-y-4">
            <div className="text-zinc-300">
              <p className="mb-2">
                Type the following phrase exactly to continue:
              </p>
              <p className="font-mono text-lg text-red-400 bg-zinc-800 p-2 rounded">
                {LIVE_CONFIRM_PHRASE}
              </p>
            </div>

            <input
              type="text"
              value={phraseInput}
              onChange={(e) => setPhraseInput(e.target.value)}
              placeholder="Type phrase here..."
              className={`w-full px-4 py-2 rounded bg-zinc-800 border-2 ${
                phraseInput.length > 0
                  ? phraseValid
                    ? "border-green-500"
                    : "border-red-500"
                  : "border-zinc-700"
              } focus:outline-none`}
              autoComplete="off"
              spellCheck={false}
            />

            <div className="flex justify-between">
              <button
                onClick={handleBack}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded"
              >
                Back
              </button>
              <button
                onClick={handlePhraseSubmit}
                disabled={!phraseValid}
                className={`px-4 py-2 rounded font-bold ${
                  phraseValid
                    ? "bg-red-700 hover:bg-red-600"
                    : "bg-zinc-700 cursor-not-allowed"
                }`}
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {/* Step: Token */}
        {step === "token" && (
          <div className="space-y-4">
            <div className="text-zinc-300">
              <p className="mb-2">
                Paste your <code className="text-red-400">LIVE_ENABLE_TOKEN</code> from your{" "}
                <code>.env</code> file:
              </p>
              <p className="text-xs text-zinc-500">
                This is a second factor to prevent accidental LIVE mode.
              </p>
            </div>

            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="Paste token here..."
              className="w-full px-4 py-2 rounded bg-zinc-800 border-2 border-zinc-700 focus:border-red-500 focus:outline-none"
              autoComplete="off"
            />

            {tokenError && (
              <div className="text-red-400 text-sm bg-red-900/30 p-2 rounded">
                {tokenError}
              </div>
            )}

            <div className="flex justify-between">
              <button
                onClick={handleBack}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded"
              >
                Back
              </button>
              <button
                onClick={handleTokenSubmit}
                disabled={tokenInput.trim().length === 0}
                className={`px-4 py-2 rounded font-bold ${
                  tokenInput.trim().length > 0
                    ? "bg-red-700 hover:bg-red-600"
                    : "bg-zinc-700 cursor-not-allowed"
                }`}
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {/* Step: Prelive Check */}
        {step === "prelive" && (
          <div className="space-y-4">
            <div className="text-zinc-300">
              <p className="mb-2">Running pre-live system check...</p>
              <p className="text-xs text-zinc-500">
                This verifies system readiness before enabling LIVE mode.
              </p>
            </div>

            {preliveResult ? (
              <div
                className={`p-4 rounded ${
                  preliveResult.passed
                    ? "bg-green-900/30 border border-green-700"
                    : "bg-red-900/30 border border-red-700"
                }`}
              >
                <div className="font-bold mb-2">
                  {preliveResult.passed ? "✓ All Checks Passed" : "✗ Checks Failed"}
                </div>
                <div className="space-y-1 text-sm">
                  {preliveResult.checks.map((check, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span>{check.passed ? "✓" : "✗"}</span>
                      <span>{check.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : preliveRunning ? (
              <div className="text-center py-8">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-red-500 border-t-transparent" />
                <p className="mt-2 text-zinc-400">Running checks...</p>
              </div>
            ) : null}

            {preliveError && (
              <div className="text-red-400 text-sm bg-red-900/30 p-2 rounded">
                {preliveError}
              </div>
            )}

            <div className="flex justify-between">
              <button
                onClick={handleBack}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded"
              >
                Back
              </button>
              {!preliveResult ? (
                <button
                  onClick={handleRunPrelive}
                  disabled={preliveRunning}
                  className={`px-4 py-2 rounded font-bold ${
                    preliveRunning
                      ? "bg-zinc-700 cursor-wait"
                      : "bg-red-700 hover:bg-red-600"
                  }`}
                >
                  {preliveRunning ? "Running..." : "Run Pre-Live Check"}
                </button>
              ) : preliveResult.passed ? (
                <button
                  onClick={() => setStep("account")}
                  className="px-4 py-2 bg-green-700 hover:bg-green-600 rounded font-bold"
                >
                  Continue
                </button>
              ) : (
                <button
                  onClick={handleRunPrelive}
                  className="px-4 py-2 bg-red-700 hover:bg-red-600 rounded font-bold"
                >
                  Retry
                </button>
              )}
            </div>
          </div>
        )}

        {/* Step: Account Confirmation */}
        {step === "account" && (
          <div className="space-y-4">
            <div className="text-zinc-300">
              <p className="mb-2">Confirm the trading account:</p>
            </div>

            <div className="bg-zinc-800 border border-zinc-700 rounded p-4">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <span className="text-zinc-500">Account ID:</span>
                <span className="font-mono text-red-400">{accountId}</span>
                <span className="text-zinc-500">Verified:</span>
                <span className="text-green-400">
                  {gates?.details.verified_account_id === accountId
                    ? "Yes"
                    : "Pending"}
                </span>
                {gates?.details.account_balance !== undefined && (
                  <>
                    <span className="text-zinc-500">Balance:</span>
                    <span>{gates.details.account_balance}</span>
                    <span className="text-zinc-500">Available:</span>
                    <span>{gates.details.account_available}</span>
                  </>
                )}
              </div>
            </div>

            <div className="bg-yellow-900/30 border border-yellow-700 rounded p-3 text-yellow-200 text-sm">
              ⚠️ Orders will be placed on this account with real funds.
            </div>

            <div className="flex justify-between">
              <button
                onClick={handleBack}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded"
              >
                Back
              </button>
              <button
                onClick={handleConfirmAccount}
                className="px-4 py-2 bg-red-700 hover:bg-red-600 rounded font-bold"
              >
                Confirm Account
              </button>
            </div>
          </div>
        )}

        {/* Step: Final Confirmation */}
        {step === "confirm" && (
          <div className="space-y-4">
            <div className="bg-red-900/50 border-2 border-red-600 rounded p-4">
              <h3 className="font-bold text-xl text-red-400 mb-2">
                FINAL CONFIRMATION
              </h3>
              <p className="text-zinc-300 mb-4">
                You are about to enable LIVE trading with real money.
              </p>
              <ul className="text-sm space-y-1 text-zinc-400">
                <li>✓ Phrase confirmed</li>
                <li>✓ Token provided</li>
                <li>✓ Pre-live check passed</li>
                <li>✓ Account verified: {accountId}</li>
              </ul>
            </div>

            <div className="flex justify-between">
              <button
                onClick={handleBack}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded"
              >
                Back
              </button>
              <button
                onClick={handleFinalConfirm}
                disabled={loading}
                className="px-6 py-3 bg-red-600 hover:bg-red-500 rounded font-bold text-lg animate-pulse"
              >
                {loading ? "Enabling..." : "ENABLE LIVE TRADING"}
              </button>
            </div>
          </div>
        )}

        {/* Step: Success */}
        {step === "success" && (
          <div className="text-center py-8">
            <div className="text-6xl mb-4">🔴</div>
            <h3 className="text-2xl font-bold text-red-500 mb-2">
              LIVE MODE ENABLED
            </h3>
            <p className="text-zinc-400">
              Trading will use real funds. Be careful.
            </p>
          </div>
        )}

        {/* Error display */}
        {error && (
          <div className="mt-4 text-red-400 text-sm bg-red-900/30 p-2 rounded">
            Error: {error}
          </div>
        )}
      </div>
    </div>
  );
}

export default GoLiveModal;
