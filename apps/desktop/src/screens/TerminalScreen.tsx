/**
 * Charts screen with multi-chart workspace.
 *
 * Wraps everything in WorkspaceProvider so all panels share a single
 * workspace state instance (fixing the independent-useState bug).
 */

import { WorkspaceProvider } from "../context/WorkspaceContext";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";

export function TerminalScreen() {
  return (
    <WorkspaceProvider>
      <div className="terminal-screen-v2">
        <WorkspaceShell />
        <div className="demo-badge">DEMO</div>
      </div>
    </WorkspaceProvider>
  );
}
