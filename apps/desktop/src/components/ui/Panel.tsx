/**
 * Panel/Card component with header and internal scroll.
 *
 * Used as the standard container for dashboard widgets, tables, etc.
 * Supports optional info icon (InfoTip) and action buttons in header.
 */

import { ReactNode } from "react";

interface PanelProps {
  title?: string;
  subtitle?: string;
  headerRight?: ReactNode;
  children: ReactNode;
  className?: string;
  noPad?: boolean;
  scrollable?: boolean;
}

export function Panel({
  title,
  subtitle,
  headerRight,
  children,
  className = "",
  noPad = false,
  scrollable = true,
}: PanelProps) {
  return (
    <div className={`ui-panel ${className}`}>
      {title && (
        <div className="ui-panel-header">
          <div className="ui-panel-header-left">
            <span className="ui-panel-title">{title}</span>
            {subtitle && <span className="ui-panel-subtitle">{subtitle}</span>}
          </div>
          {headerRight && <div className="ui-panel-header-right">{headerRight}</div>}
        </div>
      )}
      <div className={`ui-panel-body ${scrollable ? "ui-panel-scroll" : ""} ${noPad ? "ui-panel-no-pad" : ""}`}>
        {children}
      </div>
    </div>
  );
}
