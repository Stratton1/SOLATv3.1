/**
 * Terminal screen with multi-chart workspace.
 *
 * Provides:
 * - WorkspaceShell with layout management
 * - Multi-chart panels with independent symbol/timeframe
 * - Strategy drawer for bot configuration
 */

import { useState, useCallback } from "react";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { StrategyDrawer } from "../components/strategy/StrategyDrawer";

export function TerminalScreen() {
  const [showStrategy, setShowStrategy] = useState(false);

  const handleOpenStrategy = useCallback(() => {
    setShowStrategy(true);
  }, []);

  const handleCloseStrategy = useCallback(() => {
    setShowStrategy(false);
  }, []);

  return (
    <div className="terminal-screen-v2">
      <WorkspaceShell onOpenStrategy={handleOpenStrategy} />

      {showStrategy && (
        <StrategyDrawer onClose={handleCloseStrategy} />
      )}

      {/* Demo Mode Badge */}
      <div className="demo-badge">DEMO</div>
    </div>
  );
}
