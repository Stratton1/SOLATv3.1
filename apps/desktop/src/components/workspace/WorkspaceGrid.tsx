/**
 * Workspace grid - renders panels in configured layout.
 * Supports focus mode: when focusedPanelId is set, only that panel renders.
 */

import { Workspace, getLayoutGridInfo } from "../../lib/workspace";
import { ChartPanel } from "./ChartPanel";

interface WorkspaceGridProps {
  workspace: Workspace;
  focusedPanelId?: string | null;
  onMaximize?: (panelId: string) => void;
}

export function WorkspaceGrid({ workspace, focusedPanelId, onMaximize }: WorkspaceGridProps) {
  const { layout, panels } = workspace;

  // Focus mode: render only the focused panel
  if (focusedPanelId) {
    const focusedPanel = panels.find((p) => p.id === focusedPanelId);
    if (focusedPanel) {
      return (
        <div className="workspace-grid" style={{ display: "grid", gridTemplateColumns: "1fr", gridTemplateRows: "1fr", gap: "4px", height: "100%", padding: "4px" }}>
          <ChartPanel
            key={focusedPanel.id}
            panel={focusedPanel}
            index={0}
            isOnlyPanel
            onMaximize={onMaximize}
            canMaximize={false}
          />
        </div>
      );
    }
  }

  const gridInfo = getLayoutGridInfo(layout);

  const gridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: gridInfo.template,
    gridTemplateRows: layout === "four" ? "1fr 1fr" : "1fr",
    gap: "4px",
    height: "100%",
    padding: "4px",
  };

  const isMultiPanel = panels.length > 1;

  return (
    <div className="workspace-grid" style={gridStyle}>
      {panels.map((panel, index) => (
        <ChartPanel
          key={panel.id}
          panel={panel}
          index={index}
          isOnlyPanel={panels.length === 1}
          onMaximize={isMultiPanel ? onMaximize : undefined}
          canMaximize={isMultiPanel}
        />
      ))}
    </div>
  );
}
