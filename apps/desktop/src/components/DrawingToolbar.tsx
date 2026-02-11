/**
 * Drawing tool selector — appears in panel header when panel is focused.
 */

import { DrawingTool } from "../lib/drawings";

interface DrawingToolbarProps {
  activeTool: DrawingTool;
  onToolChange: (tool: DrawingTool) => void;
}

const TOOLS: Array<{ tool: DrawingTool; icon: string; label: string }> = [
  { tool: "select", icon: "\u2190", label: "Select" },
  { tool: "horizontal", icon: "\u2500", label: "Horizontal Line" },
  { tool: "trendline", icon: "\u2571", label: "Trendline" },
  { tool: "ray", icon: "\u2192", label: "Ray" },
  { tool: "rectangle", icon: "\u25A1", label: "Rectangle" },
];

export function DrawingToolbar({ activeTool, onToolChange }: DrawingToolbarProps) {
  return (
    <div className="drawing-toolbar">
      {TOOLS.map(({ tool, icon, label }) => (
        <button
          key={tool}
          className={`drawing-tool-btn ${activeTool === tool ? "active" : ""}`}
          onClick={() => onToolChange(tool)}
          title={label}
        >
          {icon}
        </button>
      ))}
    </div>
  );
}
