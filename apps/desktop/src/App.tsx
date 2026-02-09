import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import { StatusScreen } from "./components/StatusScreen";
import { TerminalScreen } from "./screens/TerminalScreen";
import { BacktestsScreen } from "./screens/BacktestsScreen";
import { BlotterScreen } from "./screens/BlotterScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { OfflineBanner } from "./components/OfflineBanner";
import { RouteErrorBoundary } from "./components/ErrorBoundary";
import { useEngineHealth } from "./hooks/useEngineHealth";
import { useWebSocket } from "./hooks/useWebSocket";

function AppContent() {
  const location = useLocation();
  const {
    health,
    config,
    isLoading,
    error,
    connectionState,
    retryCount,
    nextRetryIn,
    manualRetry,
  } = useEngineHealth();
  const { heartbeatCount, isConnected, connectionStatus } = useWebSocket();
  const [sidecarStarting, setSidecarStarting] = useState(true);

  // Wait a moment for sidecar to start
  useEffect(() => {
    const timer = setTimeout(() => {
      setSidecarStarting(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  const isTerminal = location.pathname === "/terminal";
  const isFullScreen = isTerminal;

  // Determine effective connection state
  const effectiveConnectionState = sidecarStarting
    ? "connecting"
    : connectionState;

  return (
    <div className={`app ${isFullScreen ? "terminal-mode" : ""}`}>
      <header className="app-header">
        <div className="app-title">
          <img src="/image_logo.png" alt="SOLAT" className="logo" />
          <h1>SOLAT</h1>
          <span className="version">v3.1</span>
        </div>

        <nav className="app-nav">
          <Link
            to="/"
            className={`nav-link ${location.pathname === "/" ? "active" : ""}`}
          >
            Status
          </Link>
          <Link
            to="/terminal"
            className={`nav-link ${location.pathname === "/terminal" ? "active" : ""}`}
          >
            Terminal
          </Link>
          <Link
            to="/backtests"
            className={`nav-link ${location.pathname === "/backtests" ? "active" : ""}`}
          >
            Backtests
          </Link>
          <Link
            to="/blotter"
            className={`nav-link ${location.pathname === "/blotter" ? "active" : ""}`}
          >
            Blotter
          </Link>
          <Link
            to="/settings"
            className={`nav-link ${location.pathname === "/settings" ? "active" : ""}`}
          >
            Settings
          </Link>
        </nav>

        <div className="connection-status">
          <span
            className={`status-dot ${
              isConnected ? "connected" : sidecarStarting ? "starting" : "disconnected"
            }`}
          />
          <span className="status-text">{connectionStatus}</span>
        </div>
      </header>

      {/* Engine offline warning banner */}
      {effectiveConnectionState !== "connected" && !isLoading && (
        <OfflineBanner
          connectionState={effectiveConnectionState}
          error={error}
          retryCount={retryCount}
          nextRetryIn={nextRetryIn}
          onRetry={manualRetry}
        />
      )}

      <main className={`app-main ${isTerminal ? "terminal-main-container" : ""}`}>
        <Routes>
          <Route
            path="/"
            element={
              <RouteErrorBoundary>
                <StatusScreen
                  health={health}
                  config={config}
                  heartbeatCount={heartbeatCount}
                  isLoading={isLoading || sidecarStarting}
                  error={sidecarStarting ? null : error}
                  wsConnected={isConnected}
                />
              </RouteErrorBoundary>
            }
          />
          <Route path="/terminal" element={<RouteErrorBoundary><TerminalScreen /></RouteErrorBoundary>} />
          <Route path="/backtests" element={<RouteErrorBoundary><BacktestsScreen /></RouteErrorBoundary>} />
          <Route path="/blotter" element={<RouteErrorBoundary><BlotterScreen /></RouteErrorBoundary>} />
          <Route path="/settings" element={<RouteErrorBoundary><SettingsScreen /></RouteErrorBoundary>} />
        </Routes>
      </main>

      {!isTerminal && (
        <footer className="app-footer">
          <span>SOLAT Trading Terminal</span>
          <span className="separator">|</span>
          <span>Mode: {config?.mode ?? "—"}</span>
          <span className="separator">|</span>
          <span>Engine: {health?.version ?? "—"}</span>
        </footer>
      )}
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

export default App;
