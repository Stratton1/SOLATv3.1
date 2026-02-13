import { useState } from "react";
import { BrowserRouter, Routes, Route, Link, useLocation, useNavigate } from "react-router-dom";
import { StatusScreen } from "./components/StatusScreen";
import { SplashScreen } from "./components/SplashScreen";
import { DashboardScreen } from "./screens/DashboardScreen";
import { TerminalScreen } from "./screens/TerminalScreen";
import { BacktestsScreen } from "./screens/BacktestsScreen";
import { OptimizationScreen } from "./screens/OptimizationScreen";
import { BlotterScreen } from "./screens/BlotterScreen";

import { OfflineBanner } from "./components/OfflineBanner";
import { RouteErrorBoundary } from "./components/ErrorBoundary";
import { StatusStrip } from "./components/StatusStrip";
import { CommandPalette } from "./components/CommandPalette";
import { ToastProvider } from "./context/ToastContext";
import { useEngineHealth } from "./hooks/useEngineHealth";
import { useEngineLauncher } from "./hooks/useEngineLauncher";
import { useWebSocket } from "./hooks/useWebSocket";
import { useHotkeys } from "./hooks/useHotkeys";
import { GuideDrawer } from "./components/GuideDrawer";

function AppContent() {
  const location = useLocation();
  const navigate = useNavigate();
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
  const { startEngine, isStarting: isStartingEngine } = useEngineLauncher();

  // Command palette + guide state
  const [showPalette, setShowPalette] = useState(false);
  const [showGuide, setShowGuide] = useState(false);

  // Global hotkeys — 6 tabs: Dashboard, Charts, Backtests, Optimise, Blotter, System
  const NAV_ROUTES = ["/", "/terminal", "/backtests", "/optimise", "/blotter", "/system"];
  useHotkeys({
    "Meta+k": () => setShowPalette(true),
    "Meta+1": () => navigate(NAV_ROUTES[0]),
    "Meta+2": () => navigate(NAV_ROUTES[1]),
    "Meta+3": () => navigate(NAV_ROUTES[2]),
    "Meta+4": () => navigate(NAV_ROUTES[3]),
    "Meta+5": () => navigate(NAV_ROUTES[4]),
    "Meta+6": () => navigate(NAV_ROUTES[5]),
    "Escape": () => setShowPalette(false),
  });

  const isTerminal = location.pathname === "/terminal";
  const isFullScreen = isTerminal;

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
            Dashboard
          </Link>
          <Link
            to="/terminal"
            className={`nav-link ${location.pathname === "/terminal" ? "active" : ""}`}
          >
            Charts
          </Link>
          <Link
            to="/backtests"
            className={`nav-link ${location.pathname === "/backtests" ? "active" : ""}`}
          >
            Backtests
          </Link>
          <Link
            to="/optimise"
            className={`nav-link ${location.pathname === "/optimise" ? "active" : ""}`}
          >
            Optimise
          </Link>
          <Link
            to="/blotter"
            className={`nav-link ${location.pathname === "/blotter" ? "active" : ""}`}
          >
            Blotter
          </Link>
          <Link
            to="/system"
            className={`nav-link ${location.pathname === "/system" ? "active" : ""}`}
          >
            System
          </Link>
        </nav>

        <div className="connection-status">
          <span
            className={`status-dot ${
              isConnected ? "connected" : "disconnected"
            }`}
          />
          <span className="status-text">{connectionStatus}</span>
          <button
            className="guide-trigger"
            onClick={() => setShowGuide(true)}
            title="Platform Guide"
          >
            ?
          </button>
        </div>
      </header>

      {/* Engine offline warning banner */}
      {connectionState !== "connected" && !isLoading && (
        <OfflineBanner
          connectionState={connectionState}
          error={error}
          retryCount={retryCount}
          nextRetryIn={nextRetryIn}
          onRetry={manualRetry}
          onStartEngine={startEngine}
          isStartingEngine={isStartingEngine}
        />
      )}

      <main className={`app-main ${isTerminal ? "terminal-main-container" : ""}`}>
        <Routes>
          <Route path="/" element={<RouteErrorBoundary><DashboardScreen /></RouteErrorBoundary>} />
          <Route path="/terminal" element={<RouteErrorBoundary><TerminalScreen /></RouteErrorBoundary>} />
          <Route path="/backtests" element={<RouteErrorBoundary><BacktestsScreen /></RouteErrorBoundary>} />
          <Route path="/optimise" element={<RouteErrorBoundary><OptimizationScreen /></RouteErrorBoundary>} />
          <Route path="/blotter" element={<RouteErrorBoundary><BlotterScreen /></RouteErrorBoundary>} />
          <Route
            path="/system"
            element={
              <RouteErrorBoundary>
                <StatusScreen
                  health={health}
                  config={config}
                  heartbeatCount={heartbeatCount}
                  isLoading={isLoading}
                  error={error}
                  wsConnected={isConnected}
                  onStartEngine={startEngine}
                  isStartingEngine={isStartingEngine}
                />
              </RouteErrorBoundary>
            }
          />
        </Routes>
      </main>

      {!isTerminal && (
        <StatusStrip
          mode={config?.mode ?? null}
          engineVersion={health?.version ?? null}
          isConnected={isConnected}
          currentPath={location.pathname}
        />
      )}

      {/* Command Palette */}
      {showPalette && (
        <CommandPalette
          onClose={() => setShowPalette(false)}
          onNavigate={(path) => {
            navigate(path);
            setShowPalette(false);
          }}
        />
      )}

      {/* Platform Guide */}
      <GuideDrawer isOpen={showGuide} onClose={() => setShowGuide(false)} />
    </div>
  );
}

function App() {
  const [booted, setBooted] = useState(false);
  const { startEngine } = useEngineLauncher();

  if (!booted) {
    return <SplashScreen onReady={() => setBooted(true)} onStartEngine={startEngine} />;
  }

  return (
    <BrowserRouter>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </BrowserRouter>
  );
}

export default App;
