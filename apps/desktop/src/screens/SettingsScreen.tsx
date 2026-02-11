/**
 * Settings Screen - Configuration and diagnostics view.
 *
 * Sections:
 * 1. Engine - mode, port, data directory
 * 2. IG Connectivity - status, test login
 * 3. Execution Safety - gate status, risk limits
 * 4. Data - bars store summary
 * 5. About - versions
 *
 * SECURITY: Never displays plaintext secrets.
 */

import { useState, useEffect, useCallback } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { writeTextFile } from "@tauri-apps/plugin-fs";
import { open } from "@tauri-apps/plugin-shell";
import { engineClient, DataSummaryResponse, DataSyncResponse } from "../lib/engineClient";
import { useLiveGates } from "../hooks/useLiveGates";
import { InfoTip } from "../components/InfoTip";

interface IGTestResult {
  ok: boolean;
  message?: string;
  account_id?: string;
  mode?: string;
  timestamp?: string;
}

export function SettingsScreen() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [dataSummary, setDataSummary] = useState<DataSummaryResponse | null>(null);
  const [igTestResult, setIgTestResult] = useState<IGTestResult | null>(null);
  const [igTesting, setIgTesting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Data sync state
  const [syncing, setSyncing] = useState(false);
  const [syncDays, setSyncDays] = useState(30);
  const [syncResult, setSyncResult] = useState<DataSyncResponse | null>(null);

  // Derive all state
  const [deriving, setDeriving] = useState(false);
  const [deriveResult, setDeriveResult] = useState<{ ok: boolean; message: string } | null>(null);

  const { gates, isLiveMode, blockers, warnings, refreshGates } = useLiveGates();

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [configRes, healthRes] = await Promise.all([
        engineClient.getConfig(),
        engineClient.getHealth(),
      ]);

      setConfig(configRes as unknown as Record<string, unknown>);
      setHealth(healthRes as unknown as Record<string, unknown>);

      // Fetch data summary
      try {
        const summary = await engineClient.getDataSummary();
        setDataSummary(summary);
      } catch {
        // Data endpoint may not exist or no data yet
        setDataSummary(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch settings");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleQuickSync = async () => {
    setSyncing(true);
    setSyncResult(null);

    try {
      const result = await engineClient.quickSync(syncDays);
      setSyncResult(result);

      // Refresh data summary after sync starts
      if (result.ok) {
        // Poll for completion since it's a background job
        setTimeout(async () => {
          try {
            const summary = await engineClient.getDataSummary();
            setDataSummary(summary);
          } catch {
            // Ignore
          }
        }, 2000);
      }
    } catch (err) {
      setSyncResult({
        ok: false,
        run_id: "",
        message: err instanceof Error ? err.message : "Sync failed",
        errors: [err instanceof Error ? err.message : "Unknown error"],
      });
    } finally {
      setSyncing(false);
    }
  };

  const handleDeriveAll = async () => {
    setDeriving(true);
    setDeriveResult(null);
    try {
      const result = await engineClient.deriveAll();
      setDeriveResult(result);
    } catch (err) {
      setDeriveResult({
        ok: false,
        message: err instanceof Error ? err.message : "Derive failed",
      });
    } finally {
      setDeriving(false);
    }
  };

  const revealInFinder = (path: string) => {
    open(path);
  };

  useEffect(() => {
    fetchData();
    refreshGates();
  }, [fetchData, refreshGates]);

  const handleTestIG = async () => {
    setIgTesting(true);
    setIgTestResult(null);

    try {
      const result = await engineClient.testIGLogin();
      setIgTestResult({
        ok: result.ok,
        message: result.message,
        account_id: result.current_account_id,
        mode: result.mode,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      setIgTestResult({
        ok: false,
        message: err instanceof Error ? err.message : "Test failed",
        timestamp: new Date().toISOString(),
      });
    } finally {
      setIgTesting(false);
    }
  };

  const handleExportDiagnostics = async () => {
    setExporting(true);
    setExportMessage(null);

    try {
      // Gather diagnostics from engine
      const bundle = await engineClient.getDiagnosticsBundle();

      // Ask user where to save
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const defaultName = `solat-diagnostics-${timestamp}.json`;

      const filePath = await save({
        defaultPath: defaultName,
        filters: [{ name: "JSON", extensions: ["json"] }],
      });

      if (!filePath) {
        setExportMessage("Export cancelled");
        return;
      }

      // Write file
      const content = JSON.stringify(bundle, null, 2);
      await writeTextFile(filePath, content);

      setExportMessage(`Saved to ${filePath}`);
    } catch (err) {
      setExportMessage(
        `Export failed: ${err instanceof Error ? err.message : "Unknown error"}`
      );
    } finally {
      setExporting(false);
    }
  };

  const formatPath = (path: string | undefined) => {
    if (!path) return "—";
    // Shorten home directory
    const home = path.replace(/^\/Users\/[^/]+/, "~");
    if (home.length > 40) {
      return "..." + home.slice(-37);
    }
    return home;
  };

  if (loading) {
    return (
      <div className="settings-screen">
        <div className="settings-loading">Loading settings...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="settings-screen">
        <div className="settings-error">
          <p>Failed to load settings: {error}</p>
          <button onClick={fetchData}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-screen">
      <h2 className="settings-title">Settings</h2>

      {/* Engine Section */}
      <section className="settings-section">
        <h3 className="section-title">
          Engine
          <InfoTip text="Core engine configuration. The engine runs as a Python FastAPI sidecar on localhost:8765. Mode controls whether trades are paper (DEMO) or real (LIVE)." />
        </h3>
        <div className="settings-grid">
          <div className="setting-row">
            <span className="setting-label">Mode</span>
            <span className={`setting-value mode-${(config?.mode as string)?.toLowerCase()}`}>
              {(config?.mode as string) || "—"}
            </span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Version</span>
            <span className="setting-value">{(health?.version as string) || "—"}</span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Port</span>
            <span className="setting-value">8765</span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Data Directory</span>
            <span className="setting-value" title={config?.data_dir as string}>
              {formatPath(config?.data_dir as string)}
            </span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Uptime</span>
            <span className="setting-value">
              {health?.uptime_seconds
                ? `${Math.floor((health.uptime_seconds as number) / 60)}m ${Math.floor((health.uptime_seconds as number) % 60)}s`
                : "—"}
            </span>
          </div>
        </div>
      </section>

      {/* Data Locations Section */}
      <section className="settings-section">
        <h3 className="section-title">
          Data Locations
          <InfoTip text="Filesystem paths where bars, backtests, sweeps, and proposals are stored. Use Reveal to open the directory in Finder." />
        </h3>
        <div className="settings-grid">
          {[
            { label: "Bars (Parquet)", path: (config as Record<string, unknown>)?.bars_path as string },
            { label: "Backtests", path: (config as Record<string, unknown>)?.backtests_path as string },
            { label: "Sweeps", path: (config as Record<string, unknown>)?.sweeps_path as string },
            { label: "Proposals", path: (config as Record<string, unknown>)?.proposals_path as string },
          ].map(({ label, path }) => (
            <div className="setting-row" key={label}>
              <span className="setting-label">{label}</span>
              <span className="setting-value" title={path || ""}>
                {formatPath(path)}
                {path && (
                  <button
                    className="btn-inline"
                    onClick={() => revealInFinder(path)}
                    title="Reveal in Finder"
                  >
                    Reveal
                  </button>
                )}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* IG Connectivity Section */}
      <section className="settings-section">
        <h3 className="section-title">
          IG Connectivity
          <InfoTip text="IG Markets broker integration. Requires API key, username, and password in your .env file. Test Login verifies credentials without placing any orders." />
        </h3>
        <div className="settings-grid">
          <div className="setting-row">
            <span className="setting-label">Configured</span>
            <span className={`setting-value ${config?.ig_configured ? "text-green" : "text-yellow"}`}>
              {config?.ig_configured ? "Yes" : "No"}
            </span>
          </div>
          {igTestResult && (
            <>
              <div className="setting-row">
                <span className="setting-label">Last Test</span>
                <span className={`setting-value ${igTestResult.ok ? "text-green" : "text-red"}`}>
                  {igTestResult.ok ? "Success" : "Failed"}
                </span>
              </div>
              {igTestResult.ok && igTestResult.account_id && (
                <div className="setting-row">
                  <span className="setting-label">Account ID</span>
                  <span className="setting-value">{igTestResult.account_id}</span>
                </div>
              )}
              {igTestResult.message && (
                <div className="setting-row">
                  <span className="setting-label">Message</span>
                  <span className="setting-value">{igTestResult.message}</span>
                </div>
              )}
            </>
          )}
        </div>
        <div className="setting-actions">
          <button
            className="btn btn-secondary"
            onClick={handleTestIG}
            disabled={igTesting || !config?.ig_configured}
          >
            {igTesting ? "Testing..." : "Test IG Login"}
          </button>
        </div>
      </section>

      {/* Execution Safety Section */}
      <section className="settings-section">
        <h3 className="section-title">
          Execution Safety
          <InfoTip text="Safety gates that must be satisfied before LIVE trading is allowed. Blockers prevent live mode entirely; warnings are advisory. Risk limits are configured in the engine and cannot be changed from the UI." />
        </h3>
        <div className="settings-grid">
          <div className="setting-row">
            <span className="setting-label">LIVE Allowed</span>
            <span className={`setting-value ${gates?.allowed ? "text-green" : "text-red"}`}>
              {gates?.allowed ? "Yes" : "No"}
            </span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Current Mode</span>
            <span className={`setting-value ${isLiveMode ? "text-red" : "text-green"}`}>
              {isLiveMode ? "LIVE" : "DEMO"}
            </span>
          </div>
          {blockers.length > 0 && (
            <div className="setting-row full-width">
              <span className="setting-label">Blockers</span>
              <ul className="setting-list text-red">
                {blockers.slice(0, 5).map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
                {blockers.length > 5 && <li>...and {blockers.length - 5} more</li>}
              </ul>
            </div>
          )}
          {warnings.length > 0 && (
            <div className="setting-row full-width">
              <span className="setting-label">Warnings</span>
              <ul className="setting-list text-yellow">
                {warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <h4 className="subsection-title">Risk Limits (Read-only)</h4>
        <div className="settings-grid">
          <div className="setting-row">
            <span className="setting-label">Max Position Size</span>
            <span className="setting-value">
              {(config as Record<string, unknown>)?.max_position_size?.toString() || "—"}
            </span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Max Concurrent Positions</span>
            <span className="setting-value">
              {(config as Record<string, unknown>)?.max_concurrent_positions?.toString() || "—"}
            </span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Max Daily Loss %</span>
            <span className="setting-value">
              {(config as Record<string, unknown>)?.max_daily_loss_pct?.toString() || "—"}%
            </span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Max Trades/Hour</span>
            <span className="setting-value">
              {(config as Record<string, unknown>)?.max_trades_per_hour?.toString() || "—"}
            </span>
          </div>
        </div>
      </section>

      {/* Data Section */}
      <section className="settings-section">
        <h3 className="section-title">
          Historical Data
          <InfoTip text="Parquet bar data stored locally for backtesting and strategy evaluation. Use Quick Sync to download data from IG Markets. Data is stored per symbol and timeframe." />
        </h3>
        {dataSummary && dataSummary.summaries.length > 0 ? (
          <>
            <div className="settings-grid">
              <div className="setting-row">
                <span className="setting-label">Symbols Stored</span>
                <span className="setting-value">{dataSummary.total_symbols}</span>
              </div>
              <div className="setting-row">
                <span className="setting-label">Total Bars</span>
                <span className="setting-value">
                  {dataSummary.total_bars.toLocaleString()}
                </span>
              </div>
            </div>
            <h4 className="subsection-title">Data by Symbol/Timeframe</h4>
            <div className="data-summary-table">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Timeframe</th>
                    <th>Bars</th>
                    <th>Range</th>
                  </tr>
                </thead>
                <tbody>
                  {dataSummary.summaries.slice(0, 10).map((item, i) => (
                    <tr key={i}>
                      <td>{item.symbol}</td>
                      <td>{item.timeframe}</td>
                      <td>{item.row_count?.toLocaleString()}</td>
                      <td>
                        {item.start_ts && item.end_ts
                          ? `${item.start_ts.split("T")[0]} → ${item.end_ts.split("T")[0]}`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                  {dataSummary.summaries.length > 10 && (
                    <tr>
                      <td colSpan={4} className="text-muted">
                        ...and {dataSummary.summaries.length - 10} more
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="settings-empty">
            <p>No historical data stored yet.</p>
            <p className="text-muted">Use Quick Sync below to fetch data from IG.</p>
          </div>
        )}

        <h4 className="subsection-title">Sync Data from IG</h4>
        <div className="sync-controls">
          <div className="setting-row">
            <span className="setting-label">Days to fetch</span>
            <input
              type="number"
              className="input-small"
              value={syncDays}
              onChange={(e) => setSyncDays(Math.max(1, Math.min(365, parseInt(e.target.value) || 30)))}
              min={1}
              max={365}
              disabled={syncing}
            />
          </div>
          <div className="setting-actions">
            <button
              className="btn btn-primary"
              onClick={handleQuickSync}
              disabled={syncing || !config?.ig_configured}
            >
              {syncing ? "Syncing..." : "Quick Sync (All Symbols)"}
            </button>
          </div>
          {!config?.ig_configured && (
            <p className="text-yellow setting-note">
              IG credentials not configured. Set IG_API_KEY, IG_USERNAME, IG_PASSWORD in .env
            </p>
          )}
          {syncResult && (
            <div className={`sync-result ${syncResult.ok ? "text-green" : "text-red"}`}>
              <p>
                <strong>{syncResult.ok ? "✓" : "✗"}</strong> {syncResult.message}
              </p>
              {syncResult.run_id && (
                <p className="text-muted">Run ID: {syncResult.run_id}</p>
              )}
              {syncResult.errors && syncResult.errors.length > 0 && (
                <ul>
                  {syncResult.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <h4 className="subsection-title">Derive All Timeframes</h4>
        <div className="sync-controls">
          <p className="text-muted setting-note">
            Derive 15m, 30m, 1h, 4h bars from existing 1m data for all symbols.
          </p>
          <div className="setting-actions">
            <button
              className="btn btn-secondary"
              onClick={handleDeriveAll}
              disabled={deriving}
            >
              {deriving ? "Deriving..." : "Derive All Timeframes"}
            </button>
          </div>
          {deriveResult && (
            <div className={`sync-result ${deriveResult.ok ? "text-green" : "text-red"}`}>
              <p>
                <strong>{deriveResult.ok ? "\u2713" : "\u2717"}</strong> {deriveResult.message}
              </p>
            </div>
          )}
        </div>
      </section>

      {/* About Section */}
      <section className="settings-section">
        <h3 className="section-title">About</h3>
        <div className="settings-grid">
          <div className="setting-row">
            <span className="setting-label">Engine Version</span>
            <span className="setting-value">{(health?.version as string) || "—"}</span>
          </div>
          <div className="setting-row">
            <span className="setting-label">UI Version</span>
            <span className="setting-value">3.1.0</span>
          </div>
          <div className="setting-row">
            <span className="setting-label">Environment</span>
            <span className="setting-value">{(config?.env as string) || "—"}</span>
          </div>
        </div>
        <h4 className="subsection-title">Diagnostics</h4>
        <div className="setting-actions">
          <button
            className="btn btn-secondary"
            onClick={handleExportDiagnostics}
            disabled={exporting}
          >
            {exporting ? "Exporting..." : "Export Diagnostics"}
          </button>
          {exportMessage && (
            <span className={`export-message ${exportMessage.includes("failed") ? "text-red" : "text-green"}`}>
              {exportMessage}
            </span>
          )}
        </div>
        <div className="settings-footer">
          <p className="settings-note">
            Credentials are stored in <code>.env</code> file only.
            Secrets are never displayed in this UI.
          </p>
        </div>
      </section>
    </div>
  );
}

export default SettingsScreen;
