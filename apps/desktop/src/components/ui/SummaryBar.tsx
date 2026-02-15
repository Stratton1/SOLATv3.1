/**
 * Collapsible SummaryBar component — appears at the top of every page.
 *
 * Provides:
 * - Page purpose (1–2 lines)
 * - Next actions (2–4 bullets)
 * - Status chips (mode, broker, engine, etc.)
 *
 * Persists collapsed/expanded state per-page in localStorage.
 */

import { useState, useEffect, useCallback } from "react";

export interface StatusChip {
  label: string;
  value: string;
  variant?: "default" | "success" | "warning" | "danger" | "info";
}

interface SummaryBarProps {
  pageId: string;
  title: string;
  description: string;
  actions?: string[];
  chips?: StatusChip[];
}

const STORAGE_KEY_PREFIX = "solat_summary_";

function getStoredState(pageId: string): boolean {
  try {
    const val = localStorage.getItem(`${STORAGE_KEY_PREFIX}${pageId}`);
    if (val === null) return true; // default expanded on first visit
    return val === "1";
  } catch {
    return true;
  }
}

function setStoredState(pageId: string, expanded: boolean) {
  try {
    localStorage.setItem(`${STORAGE_KEY_PREFIX}${pageId}`, expanded ? "1" : "0");
  } catch {
    // ignore
  }
}

export function SummaryBar({ pageId, title, description, actions, chips }: SummaryBarProps) {
  const [expanded, setExpanded] = useState(() => getStoredState(pageId));

  useEffect(() => {
    setExpanded(getStoredState(pageId));
  }, [pageId]);

  const toggle = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev;
      setStoredState(pageId, next);
      return next;
    });
  }, [pageId]);

  const chipVariantClass = (v?: string) => {
    switch (v) {
      case "success": return "chip-success";
      case "warning": return "chip-warning";
      case "danger": return "chip-danger";
      case "info": return "chip-info";
      default: return "chip-default";
    }
  };

  return (
    <div className={`summary-bar ${expanded ? "summary-bar-expanded" : "summary-bar-collapsed"}`}>
      <div className="summary-bar-header" onClick={toggle} role="button" tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") toggle(); }}>
        <div className="summary-bar-title-row">
          <span className="summary-bar-title">{title}</span>
          {!expanded && chips && chips.length > 0 && (
            <div className="summary-bar-chips-inline">
              {chips.map((c, i) => (
                <span key={i} className={`summary-chip ${chipVariantClass(c.variant)}`}>
                  {c.label}: {c.value}
                </span>
              ))}
            </div>
          )}
        </div>
        <button className="summary-bar-toggle" aria-label={expanded ? "Collapse" : "Expand"}>
          <span className={`summary-chevron ${expanded ? "chevron-up" : "chevron-down"}`}>&#x25B8;</span>
        </button>
      </div>

      {expanded && (
        <div className="summary-bar-body">
          <p className="summary-bar-desc">{description}</p>

          <div className="summary-bar-lower">
            {actions && actions.length > 0 && (
              <div className="summary-bar-actions">
                <span className="summary-bar-actions-label">Next actions:</span>
                <ul className="summary-bar-action-list">
                  {actions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </div>
            )}

            {chips && chips.length > 0 && (
              <div className="summary-bar-chips">
                {chips.map((c, i) => (
                  <span key={i} className={`summary-chip ${chipVariantClass(c.variant)}`}>
                    <span className="chip-label">{c.label}</span>
                    <span className="chip-value">{c.value}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
