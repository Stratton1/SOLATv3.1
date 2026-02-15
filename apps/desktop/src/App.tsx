import { useState } from "react";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import { StatusScreen } from "./components/StatusScreen";
import { SplashScreen } from "./components/SplashScreen";
import { DashboardScreen } from "./screens/DashboardScreen";
import { TerminalScreen } from "./screens/TerminalScreen";
import { BacktestsScreen } from "./screens/BacktestsScreen";
import { OptimizationScreen } from "./screens/OptimizationScreen";
import { BlotterScreen } from "./screens/BlotterScreen";
import { IntroScreen } from "./screens/IntroScreen";
import { BotsScreen } from "./screens/BotsScreen";
import { AllowlistScreen } from "./screens/AllowlistScreen";
import { PlaygroundScreen } from "./screens/PlaygroundScreen";

import { OfflineBanner } from "./components/OfflineBanner";
import { RouteErrorBoundary } from "./components/ErrorBoundary";
import { StatusStrip } from "./components/StatusStrip";
import { CommandPalette } from "./components/CommandPalette";
import { Sidebar } from "./components/Sidebar";
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

  // Global hotkeys — tabs: Home, Dashboard, Charts, Backtests, Optimise, Bots, Allowlist, Playground, Blotter, System
  const NAV_ROUTES = ["/", "/dashboard", "/terminal", "/backtests", "/optimise", "/bots", "/allowlist", "/playground", "/blotter", "/system"];
  useHotkeys({
    "Meta+k": () => setShowPalette(true),
    "Meta+1": () => navigate(NAV_ROUTES[0]),
    "Meta+2": () => navigate(NAV_ROUTES[1]),
    "Meta+3": () => navigate(NAV_ROUTES[2]),
    "Meta+4": () => navigate(NAV_ROUTES[3]),
    "Meta+5": () => navigate(NAV_ROUTES[4]),
    "Meta+6": () => navigate(NAV_ROUTES[5]),
    "Meta+7": () => navigate(NAV_ROUTES[6]),
    "Meta+8": () => navigate(NAV_ROUTES[7]),
    "Meta+9": () => navigate(NAV_ROUTES[8]),
    "Meta+0": () => navigate(NAV_ROUTES[9]),
    "Escape": () => setShowPalette(false),
  });

  const isTerminal = location.pathname === "/terminal";

  return (
    <div className="app-container">
      {/* Left Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="app-right-col">
        {/* Header */}
        <header className="app-header">
          <div className="app-title-section">
             <h2 className="section-title">
               {({
                 "/": "Home",
                 "/dashboard": "Dashboard",
                 "/terminal": "Charts",
                 "/backtests": "Backtests",
                 "/optimise": "Optimise",
                 "/bots": "Bots & Strategies",
                 "/allowlist": "Allowlist",
                 "/playground": "Playground",
                 "/blotter": "Blotter",
                 "/system": "System",
               } as Record<string, string>)[location.pathname] ?? "SOLAT"}
             </h2>
          </div>

          <div className="header-actions">
             <button className="icon-btn notification-bell" title="Notifications">
               🔔
             </button>
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
            <Route path="/" element={<RouteErrorBoundary><IntroScreen /></RouteErrorBoundary>} />
            <Route path="/dashboard" element={<RouteErrorBoundary><DashboardScreen /></RouteErrorBoundary>} />
            <Route path="/terminal" element={<RouteErrorBoundary><TerminalScreen /></RouteErrorBoundary>} />
            <Route path="/backtests" element={<RouteErrorBoundary><BacktestsScreen /></RouteErrorBoundary>} />
            <Route path="/optimise" element={<RouteErrorBoundary><OptimizationScreen /></RouteErrorBoundary>} />
            <Route path="/bots" element={<RouteErrorBoundary><BotsScreen /></RouteErrorBoundary>} />
            <Route path="/allowlist" element={<RouteErrorBoundary><AllowlistScreen /></RouteErrorBoundary>} />
            <Route path="/playground" element={<RouteErrorBoundary><PlaygroundScreen /></RouteErrorBoundary>} />
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
      </div>

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
