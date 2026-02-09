/**
 * Workspace shell - top-level container for multi-chart workspace.
 *
 * Provides:
 * - Workspace dropdown selector
 * - Layout selector
 * - Global controls
 */

import { useState, useCallback } from "react";
import { useWorkspace } from "../../hooks/useWorkspace";
import { LayoutType } from "../../lib/workspace";
import { WorkspaceGrid } from "./WorkspaceGrid";

// =============================================================================
// Types
// =============================================================================

interface WorkspaceShellProps {
  onOpenStrategy?: () => void;
}

// =============================================================================
// Layout Icons
// =============================================================================

const LayoutIcon = ({ layout }: { layout: LayoutType }) => {
  const size = 16;

  switch (layout) {
    case "single":
      return (
        <svg width={size} height={size} viewBox="0 0 16 16">
          <rect x="1" y="1" width="14" height="14" fill="currentColor" rx="1" />
        </svg>
      );
    case "two":
      return (
        <svg width={size} height={size} viewBox="0 0 16 16">
          <rect x="1" y="1" width="6" height="14" fill="currentColor" rx="1" />
          <rect x="9" y="1" width="6" height="14" fill="currentColor" rx="1" />
        </svg>
      );
    case "four":
      return (
        <svg width={size} height={size} viewBox="0 0 16 16">
          <rect x="1" y="1" width="6" height="6" fill="currentColor" rx="1" />
          <rect x="9" y="1" width="6" height="6" fill="currentColor" rx="1" />
          <rect x="1" y="9" width="6" height="6" fill="currentColor" rx="1" />
          <rect x="9" y="9" width="6" height="6" fill="currentColor" rx="1" />
        </svg>
      );
    case "six":
      return (
        <svg width={size} height={size} viewBox="0 0 16 16">
          <rect x="1" y="1" width="4" height="6" fill="currentColor" rx="0.5" />
          <rect x="6" y="1" width="4" height="6" fill="currentColor" rx="0.5" />
          <rect x="11" y="1" width="4" height="6" fill="currentColor" rx="0.5" />
          <rect x="1" y="9" width="4" height="6" fill="currentColor" rx="0.5" />
          <rect x="6" y="9" width="4" height="6" fill="currentColor" rx="0.5" />
          <rect x="11" y="9" width="4" height="6" fill="currentColor" rx="0.5" />
        </svg>
      );
  }
};

// =============================================================================
// Component
// =============================================================================

export function WorkspaceShell({ onOpenStrategy }: WorkspaceShellProps) {
  const {
    workspace,
    workspaces,
    createWorkspace,
    switchWorkspace,
    renameWorkspace,
    deleteWorkspace,
    duplicateWorkspace,
    setLayout,
  } = useWorkspace();

  const [showDropdown, setShowDropdown] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  const layouts: LayoutType[] = ["single", "two", "four", "six"];

  const handleNewWorkspace = useCallback(() => {
    const name = `Workspace ${workspaces.length + 1}`;
    createWorkspace(name);
    setShowDropdown(false);
  }, [createWorkspace, workspaces.length]);

  const handleRename = useCallback(() => {
    setIsRenaming(true);
    setRenameValue(workspace.name);
    setShowDropdown(false);
  }, [workspace.name]);

  const handleRenameSubmit = useCallback(() => {
    if (renameValue.trim()) {
      renameWorkspace(workspace.id, renameValue.trim());
    }
    setIsRenaming(false);
  }, [renameValue, renameWorkspace, workspace.id]);

  const handleDuplicate = useCallback(() => {
    duplicateWorkspace(workspace.id, `${workspace.name} (copy)`);
    setShowDropdown(false);
  }, [duplicateWorkspace, workspace.id, workspace.name]);

  const handleDelete = useCallback(() => {
    if (workspaces.length > 1) {
      deleteWorkspace(workspace.id);
    }
    setShowDropdown(false);
  }, [deleteWorkspace, workspace.id, workspaces.length]);

  return (
    <div className="workspace-shell">
      {/* Workspace Toolbar */}
      <div className="workspace-toolbar">
        <div className="toolbar-left">
          {/* Workspace Selector */}
          <div className="workspace-selector">
            {isRenaming ? (
              <input
                type="text"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onBlur={handleRenameSubmit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleRenameSubmit();
                  if (e.key === "Escape") setIsRenaming(false);
                }}
                autoFocus
                className="workspace-rename-input"
              />
            ) : (
              <button
                className="workspace-dropdown-btn"
                onClick={() => setShowDropdown(!showDropdown)}
              >
                <span className="workspace-name">{workspace.name}</span>
                <span className="dropdown-arrow">▼</span>
              </button>
            )}

            {showDropdown && (
              <div className="workspace-dropdown">
                <div className="dropdown-section">
                  <div className="dropdown-label">Workspaces</div>
                  {workspaces.map((w) => (
                    <button
                      key={w.id}
                      className={`dropdown-item ${w.id === workspace.id ? "active" : ""}`}
                      onClick={() => {
                        switchWorkspace(w.id);
                        setShowDropdown(false);
                      }}
                    >
                      {w.name}
                    </button>
                  ))}
                </div>
                <div className="dropdown-divider" />
                <button className="dropdown-item" onClick={handleNewWorkspace}>
                  + New Workspace
                </button>
                <button className="dropdown-item" onClick={handleRename}>
                  Rename
                </button>
                <button className="dropdown-item" onClick={handleDuplicate}>
                  Duplicate
                </button>
                {workspaces.length > 1 && (
                  <button
                    className="dropdown-item danger"
                    onClick={handleDelete}
                  >
                    Delete
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="toolbar-center">
          {/* Layout Selector */}
          <div className="layout-selector">
            {layouts.map((l) => (
              <button
                key={l}
                className={`layout-btn ${workspace.layout === l ? "active" : ""}`}
                onClick={() => setLayout(l)}
                title={`${l} layout`}
              >
                <LayoutIcon layout={l} />
              </button>
            ))}
          </div>
        </div>

        <div className="toolbar-right">
          {onOpenStrategy && (
            <button className="strategy-btn" onClick={onOpenStrategy}>
              Strategy
            </button>
          )}
        </div>
      </div>

      {/* Workspace Grid */}
      <div className="workspace-content">
        <WorkspaceGrid workspace={workspace} />
      </div>

      {/* Close dropdown on outside click */}
      {showDropdown && (
        <div
          className="dropdown-backdrop"
          onClick={() => setShowDropdown(false)}
        />
      )}
    </div>
  );
}
