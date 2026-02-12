import { memo, useState, useEffect, useCallback, useMemo } from "react";
import { open } from "@tauri-apps/plugin-shell";
import { engineClient, DataSummaryResponse, IGStatusResponse } from "../lib/engineClient";
import { useIgStatus } from "../hooks/useIgStatus";
import { useToast } from "../context/ToastContext";
import { InfoTip } from "../components/InfoTip";

// =============================================================================
// Types
// =============================================================================

interface IGTestResult {
  ok: boolean;
  message?: string;
  account_id?: string;
  mode?: string;
  timestamp?: string;
  environment?: string;
  base_url?: string;
  error_code?: string;
  status_code?: number;
}

// =============================================================================
// Sub-components
// =============================================================================

const EngineInfoCard = memo(function EngineInfoCard({ 
  config, 
  health, 
  formatUptime 
}: { 
  config: any; 
  health: any; 
  formatUptime: (s: number) => string 
}) {
  return (
    <div className="terminal-card">
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Engine & App
          <InfoTip text="Core system information. Port 8765 is used for internal engine communication." />
        </span>
      </div>
      <div className="terminal-card-body">
        <div className="dense-row">
          <span className="dense-label">Mode</span>
          <span className={`dense-value mode-${config?.mode?.toLowerCase()}`}>{config?.mode || "—"}</span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Engine Version</span>
          <span className="dense-value">{health?.version || "—"}</span>
        </div>
        <div className="dense-row">
          <span className="dense-label">UI Version</span>
          <span className="dense-value">3.1.0</span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Port</span>
          <span className="dense-value">8765</span>
        </div>
        <div className="dense-row">
          <span className="dense-label">Uptime</span>
          <span className="dense-value num tabular-nums">{formatUptime(health?.uptime_seconds || 0)}</span>
        </div>
      </div>
    </div>
  );
});

const DataLocationsCard = memo(function DataLocationsCard({ config, formatPath, revealInFinder }: { config: any; formatPath: any; revealInFinder: any }) {
  const { showToast } = useToast();
  
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    showToast("Path copied to clipboard", "success");
  };

  const paths = [
    { label: "Bars (Parquet)", key: "bars_path" },
    { label: "Backtests", key: "backtests_path" },
    { label: "Sweeps", key: "sweeps_path" },
    { label: "Proposals", key: "proposals_path" },
  ];

  return (
    <div className="terminal-card">
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Data Locations
          <InfoTip text="Storage paths for historical data and run artefacts. Use 'Reveal' to open the folder." />
        </span>
      </div>
      <div className="terminal-card-body">
        {paths.map((p) => (
          <div className="dense-row" key={p.key} style={{ gap: 8 }}>
            <span className="dense-label" style={{ minWidth: 80 }}>{p.label}</span>
            <div style={{ display: "flex", gap: 4, alignItems: "center", flex: 1, minWidth: 0 }}>
              <span className="dense-value" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }} title={config?.[p.key]}>
                {formatPath(config?.[p.key])}
              </span>
              <button className="btn-inline" onClick={() => copyToClipboard(config?.[p.key])}>Copy</button>
              <button className="btn-inline" onClick={() => revealInFinder(config?.[p.key])}>Reveal</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

const IGCredentialsCard = memo(function IGCredentialsCard({ 
  currentConfig, 
  igStatus 
}: { 
  currentConfig: any; 
  igStatus: IGStatusResponse | null 
}) {
  const [tab, setTab] = useState<"DEMO" | "LIVE">("DEMO");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<IGTestResult | null>(null);
  const { showToast } = useToast();

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await engineClient.testIGLogin();
      setTestResult({
        ok: result.ok,
        message: result.message,
        account_id: result.current_account_id,
        mode: result.mode,
        timestamp: new Date().toISOString(),
        environment: result.environment,
        base_url: result.base_url,
        error_code: result.error_code,
        status_code: result.status_code,
      });
      if (result.ok) showToast("IG Auth successful", "success");
      else showToast("IG Auth failed", "error");
    } catch (err) {
      setTestResult({ ok: false, message: "Test failed" });
      showToast("Test request error", "error");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="terminal-card" style={{ height: "100%" }}>
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          IG Credentials
          <InfoTip text="Configure API credentials for IG Markets. DEMO and LIVE credentials are managed separately." />
        </span>
        <div className="layout-selector" style={{ background: "var(--bg-tertiary)" }}>
          <button className={`tf-btn ${tab === "DEMO" ? "active" : ""}`} onClick={() => setTab("DEMO")}>DEMO</button>
          <button className={`tf-btn ${tab === "LIVE" ? "active" : ""}`} onClick={() => setTab("LIVE")}>LIVE</button>
        </div>
      </div>
      <div className="terminal-card-body scroll-area">
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="execution-hint" style={{ marginTop: 0, background: "var(--accent-yellow-bg)", color: "var(--accent-yellow)", fontSize: 10 }}>
            <strong>NOTE</strong>: UI editing is not yet wired to engine. Use @.env for now.
          </div>

          <div className="setting-group">
            <label className="dense-label">API Key</label>
            <input type="password" disabled className="param-input" style={{ width: "100%", textAlign: "left" }} value="********" />
          </div>
          <div className="setting-group">
            <label className="dense-label">Identifier / Username</label>
            <input type="text" disabled className="param-input" style={{ width: "100%", textAlign: "left" }} value={currentConfig?.ig_username || ""} />
          </div>
          <div className="setting-group">
            <label className="dense-label">Password</label>
            <input type="password" disabled className="param-input" style={{ width: "100%", textAlign: "left" }} value="********" />
          </div>
          <div className="setting-group">
            <label className="dense-label">Account ID</label>
            <input type="text" disabled className="param-input" style={{ width: "100%", textAlign: "left" }} value={currentConfig?.ig_account_id || ""} />
          </div>

          <div style={{ marginTop: 12, padding: 8, background: "var(--bg-tertiary)", borderRadius: 4 }}>
            <div className="dense-row">
              <span className="dense-label">Status</span>
              <span className={`dense-value ${igStatus?.authenticated ? "text-green" : "text-red"}`}>
                {igStatus?.authenticated ? "AUTHENTICATED" : "NOT CONNECTED"}
              </span>
            </div>
            <div className="dense-row">
              <span className="dense-label">Environment</span>
              <span className="dense-value">{tab}</span>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="wizard-btn primary" style={{ flex: 1 }} onClick={handleTest} disabled={testing}>
              {testing ? "Testing..." : `Test ${tab} Login`}
            </button>
            <button className="wizard-btn" style={{ flex: 1 }} disabled>Save {tab}</button>
          </div>

          {testResult && (
            <div className={`sync-result ${testResult.ok ? "text-green" : "text-red"}`} style={{ marginTop: 8, fontSize: 11, padding: 8, background: "var(--bg-app)", borderRadius: 4 }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>Last Test Result:</div>
              <div>{testResult.message}</div>
              {testResult.error_code && <div className="mono">Code: {testResult.error_code}</div>}
              {testResult.status_code && <div>HTTP: {testResult.status_code}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

const DataExplorerCard = memo(function DataExplorerCard({ dataSummary }: { dataSummary: DataSummaryResponse | null }) {
  const [search, setSearch] = useState("");
  const [deriving, setDeriving] = useState(false);
  const { showToast } = useToast();

  const handleDerive = async () => {
    setDeriving(true);
    try {
      const res = await engineClient.deriveAll();
      if (res.ok) showToast("Derive job started", "success");
      else showToast(res.message, "error");
    } catch (e) {
      showToast("Derive request failed", "error");
    } finally {
      setDeriving(false);
    }
  };

  const filtered = useMemo(() => {
    if (!dataSummary) return [];
    return dataSummary.summaries.filter(s => 
      s.symbol.toLowerCase().includes(search.toLowerCase()) || 
      s.timeframe.toLowerCase().includes(search.toLowerCase())
    );
  }, [dataSummary, search]);

  return (
    <div className="terminal-card" style={{ height: "100%", overflow: "hidden" }}>
      <div className="terminal-card-header">
        <span className="terminal-card-title">
          Historical Data
          <InfoTip text="Local OHLCV data stored in Parquet format. Used for backtesting and strategy warmup." />
        </span>
        <button className="opt-refresh-btn" onClick={handleDerive} disabled={deriving}>
          {deriving ? "..." : "DERIVE ALL"}
        </button>
      </div>
      <div className="terminal-card-body" style={{ display: "flex", flexDirection: "column", padding: 0 }}>
        {/* Summary Header */}
        <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border-color)", background: "var(--bg-app)" }}>
          <div style={{ display: "flex", gap: 16 }}>
            <div className="autopilot-metric">
              <span className="autopilot-metric-value num tabular-nums" style={{ fontSize: 14 }}>{dataSummary?.total_symbols || 0}</span>
              <span className="autopilot-metric-label">Symbols</span>
            </div>
            <div className="autopilot-metric">
              <span className="autopilot-metric-value num tabular-nums" style={{ fontSize: 14 }}>{(dataSummary?.total_bars || 0).toLocaleString()}</span>
              <span className="autopilot-metric-label">Total Bars</span>
            </div>
          </div>
          <input 
            type="text" 
            placeholder="Search symbol/timeframe..." 
            className="panel-symbol-search" 
            style={{ width: "100%", marginTop: 10, borderRadius: 4, padding: "4px 8px" }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Table Area */}
        <div className="scroll-area" style={{ flex: 1 }}>
          <table className="terminal-signals-table dense" style={{ width: "100%" }}>
            <thead style={{ position: "sticky", top: 0, zIndex: 10, background: "var(--bg-card)" }}>
              <tr>
                <th>Symbol</th>
                <th>TF</th>
                <th style={{ textAlign: "right" }}>Bars</th>
                <th>Range</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, i) => (
                <tr key={i}>
                  <td className="mono" style={{ fontWeight: 600 }}>{item.symbol}</td>
                  <td>{item.timeframe}</td>
                  <td className="mono num tabular-nums" style={{ textAlign: "right" }}>{item.row_count?.toLocaleString()}</td>
                  <td style={{ fontSize: 9, color: "var(--text-secondary)" }}>
                    {item.start_ts?.split("T")[0]} → {item.end_ts?.split("T")[0]}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={4} style={{ textAlign: "center", padding: 20, color: "var(--text-muted)" }}>NO DATA FOUND</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
});

// =============================================================================
// Main Component
// =============================================================================

export function SettingsScreen() {
  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [health, setHealth] = useState<Record<string, any> | null>(null);
  const [dataSummary, setDataSummary] = useState<DataSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const { showToast } = useToast();
  const { data: igStatus } = useIgStatus();

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [configRes, healthRes, summaryRes] = await Promise.all([
        engineClient.getConfig(),
        engineClient.getHealth(),
        engineClient.getDataSummary().catch(() => null),
      ]);
      setConfig(configRes);
      setHealth(healthRes);
      setDataSummary(summaryRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCopyDiagnostics = async () => {
    try {
      const bundle = await engineClient.getDiagnosticsBundle();
      await navigator.clipboard.writeText(JSON.stringify(bundle, null, 2));
      showToast("Diagnostics copied to clipboard", "success");
    } catch (e) {
      showToast("Failed to copy diagnostics", "error");
    }
  };

  const formatPath = (path: string | undefined) => {
    if (!path) return "—";
    const home = path.replace(/^\/Users\/[^/]+/, "~");
    if (home.length > 30) return "..." + home.slice(-27);
    return home;
  };

  const formatUptime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m ${seconds % 60}s`;
  };

  const revealInFinder = (path: string) => {
    open(path);
  };

  if (loading) return <div className="loading-container"><div className="loading-spinner" /></div>;
  if (error) return <div className="error-container"><p>{error}</p><button onClick={fetchData}>Retry</button></div>;

  return (
    <div className="status-dashboard" style={{ gridTemplateRows: "40px 1fr" }}>
      {/* Header */}
      <header className="status-dashboard-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h2 style={{ fontSize: 12, fontWeight: 800, color: "var(--text-primary)", letterSpacing: "0.1em" }}>CONFIGURATION CONSOLE</h2>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div className="led-group">
            <div className="led-item">
              <div className={`led ${health?.status === "healthy" ? "active" : "error"}`} />
              ENGINE
            </div>
            <div className="led-item">
              <div className={`led ${igStatus?.authenticated ? "active" : "warning"}`} />
              IG AUTH
            </div>
          </div>
          <button className="wizard-btn primary sm" onClick={handleCopyDiagnostics}>Copy Diagnostics</button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="status-dashboard-left">
        <EngineInfoCard config={config} health={health} formatUptime={formatUptime} />
        <DataLocationsCard config={config} formatPath={formatPath} revealInFinder={revealInFinder} />
        
        <div className="terminal-card">
          <div className="terminal-card-header">
            <span className="terminal-card-title">
              Safety & Environment
              <InfoTip text="Key safety principles for live trading." />
            </span>
          </div>
          <div className="terminal-card-body" style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>
            <p>• <strong>DEMO</strong>: Live signal testing with simulated fills.</p>
            <p>• <strong>LIVE</strong>: Real orders sent to IG Markets.</p>
            <p style={{ marginTop: 8 }}>Always complete the 5-step DEMO checklist before arming live execution.</p>
          </div>
        </div>
      </div>

      <div className="status-dashboard-mid">
        <IGCredentialsCard currentConfig={config} igStatus={igStatus} />
      </div>

      <div className="status-dashboard-right">
        <DataExplorerCard dataSummary={dataSummary} />
      </div>
    </div>
  );
}

export default SettingsScreen;
