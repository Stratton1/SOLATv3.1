/**
 * Modal component — renders into portal with backdrop.
 *
 * Uses the global z-index scale (modal = 3000).
 */

import { useEffect, useCallback, ReactNode } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  width?: number;
  closable?: boolean;
}

function getOverlayRoot(): HTMLElement {
  let root = document.getElementById("overlay-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "overlay-root";
    document.body.appendChild(root);
  }
  return root;
}

export function Modal({ isOpen, onClose, title, children, width = 520, closable = true }: ModalProps) {
  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && closable) onClose();
    },
    [onClose, closable]
  );

  useEffect(() => {
    if (!isOpen) return;
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, handleEscape]);

  if (!isOpen) return null;

  return createPortal(
    <div className="ui-modal-backdrop" onClick={closable ? onClose : undefined}>
      <div
        className="ui-modal"
        style={{ maxWidth: width }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {title && (
          <div className="ui-modal-header">
            <span className="ui-modal-title">{title}</span>
            {closable && (
              <button className="ui-modal-close" onClick={onClose} aria-label="Close">
                &times;
              </button>
            )}
          </div>
        )}
        <div className="ui-modal-body">{children}</div>
      </div>
    </div>,
    getOverlayRoot()
  );
}
