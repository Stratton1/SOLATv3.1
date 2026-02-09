/**
 * Workspace grid - renders panels in configured layout.
 */

import { Workspace, getLayoutGridInfo } from "../../lib/workspace";
import { ChartPanel } from "./ChartPanel";

interface WorkspaceGridProps {
  workspace: Workspace;
}

export function WorkspaceGrid({ workspace }: WorkspaceGridProps) {
  const { layout, panels } = workspace;
  const gridInfo = getLayoutGridInfo(layout);

  // Calculate grid style
  const gridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: gridInfo.template,
    gridTemplateRows: layout === "four" || layout === "six" ? "1fr 1fr" : "1fr",
    gap: "4px",
    height: "100%",
    padding: "4px",
  };

  return (
    <div className="workspace-grid" style={gridStyle}>
      {panels.map((panel, index) => (
        <ChartPanel
          key={panel.id}
          panel={panel}
          index={index}
          isOnlyPanel={panels.length === 1}
        />
      ))}
    </div>
  );
}
