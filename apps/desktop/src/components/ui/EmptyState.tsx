/**
 * EmptyState component — shown when a table, list, or panel has no data.
 */

import { ReactNode } from "react";

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: string;
  action?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ title, description, icon, action, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="ui-empty-state">
      {icon && <span className="ui-empty-icon">{icon}</span>}
      <p className="ui-empty-title">{title}</p>
      {description && <p className="ui-empty-desc">{description}</p>}
      {action && <div className="ui-empty-action">{action}</div>}
      {actionLabel && onAction && (
        <div className="ui-empty-action">
          <button className="btn btn-sm btn-primary" onClick={onAction}>{actionLabel}</button>
        </div>
      )}
    </div>
  );
}
