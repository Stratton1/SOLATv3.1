import { memo, useState } from "react";
import { IGStatusResponse } from "../../hooks/useBrokerStatus";
import { InfoTip } from "../InfoTip";
import { engineClient } from "../../lib/engineClient";
import { useToast } from "../../context/ToastContext";

interface BrokerConnectivityCardProps {
  status: IGStatusResponse | null;
  isLoading: boolean;
  onLoginSuccess?: () => void;
}

export const BrokerConnectivityCard = memo(function BrokerConnectivityCard({
  status,
  isLoading,
  onLoginSuccess,
}: BrokerConnectivityCardProps) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message?: string;
    account_id?: string;
  } | null>(null);
  const { showToast } = useToast();

  if (isLoading && !status) {
    return <div className="terminal-card skeleton" style={{ height: 180 }} />;
  }

  const formatSessionAge = (seconds: number | null): string => {
    if (seconds === null) return "\u2014";
    const mins = Math.floor(seconds / 60);
    if (mins < 60) return `${mins}m`;
    return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await engineClient.testIGLogin();
      setTestResult({
        ok: result.ok,
        message: result.message,
        account_id: result.current_account_id,
      });
      if (result.ok) {
        showToast("IG Auth successful", "success");
        onLoginSuccess?.();
      } else {
        showToast("IG Auth failed", "error");
      }
    } catch {
      setTestResult({ ok: false, message: "Request failed \u2014 is the engine running?" });
      showToast("Test request error", "error");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="terminal-card">
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Broker Connectivity
          <InfoTip text="IG Markets REST API status. Use Test Connection to authenticate. Credentials are configured in the engine .env file." />
        </span>
        <span className={`card-badge ${status?.authenticated ? "healthy" : "demo"}`}>
          {status?.authenticated ? "AUTHENTICATED" : "OFFLINE"}
        </span>
      </div>
      <div className="terminal-card-body">
        <div className="dense-row">
          <span className="dense-label">Account Mode</span>
          <span className={`dense-value ${status?.mode === "LIVE" ? "text-red" : "text-green"}`}>
            {status?.mode ?? "\u2014"}
          </span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Session Age</span>
          <span className="dense-value num">{formatSessionAge(status?.session_age_seconds ?? null)}</span>
        </div>
        <div className="dense-row">
          <span className="dense-label">REST Latency</span>
          <span className={`dense-value num ${status && status.metrics.last_request_latency_ms > 500 ? "text-red" : ""}`}>
            {status ? `${status.metrics.last_request_latency_ms} ms` : "\u2014"}
          </span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Rate Limit</span>
          <span className={`dense-value num ${status && status.metrics.rate_limit_usage_pct > 80 ? "text-red" : ""}`}>
            {status ? `${status.metrics.rate_limit_usage_pct}%` : "\u2014"}
          </span>
        </div>

        {/* Test Connection */}
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border-color)" }}>
          <button
            className="wizard-btn primary"
            style={{ width: "100%", padding: "6px 12px", fontSize: 11 }}
            onClick={handleTestConnection}
            disabled={testing}
          >
            {testing ? "Testing..." : status?.authenticated ? "Re-test Connection" : "Test Connection"}
          </button>
        </div>

        {testResult && (
          <div
            style={{
              marginTop: 8,
              fontSize: 10,
              padding: 8,
              background: testResult.ok ? "rgba(0,214,143,0.08)" : "rgba(244,91,105,0.08)",
              borderRadius: 4,
              border: `1px solid ${testResult.ok ? "var(--accent-green)" : "var(--accent-red)"}`,
            }}
          >
            <div style={{ fontWeight: 700, color: testResult.ok ? "var(--accent-green)" : "var(--accent-red)" }}>
              {testResult.ok ? "Connected" : "Failed"}
            </div>
            <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>{testResult.message}</div>
            {testResult.account_id && (
              <div style={{ color: "var(--text-secondary)" }}>Account: {testResult.account_id}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
});
