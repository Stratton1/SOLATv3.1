/**
 * Portal-based Popover component.
 *
 * Similar to Tooltip but stays open on click, supports richer content.
 * Renders into #overlay-root via portal.
 */

import { useState, useRef, useCallback, useEffect, ReactNode } from "react";
import { createPortal } from "react-dom";

interface PopoverProps {
  content: ReactNode;
  children: ReactNode;
  position?: "top" | "bottom" | "left" | "right";
  trigger?: "click" | "hover";
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

export function Popover({ content, children, position = "bottom", trigger = "click" }: PopoverProps) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLSpanElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const gap = 6;

    let top = 0;
    let left = 0;

    switch (position) {
      case "top":
        top = rect.top - gap;
        left = rect.left + rect.width / 2;
        break;
      case "bottom":
        top = rect.bottom + gap;
        left = rect.left + rect.width / 2;
        break;
      case "left":
        top = rect.top + rect.height / 2;
        left = rect.left - gap;
        break;
      case "right":
        top = rect.top + rect.height / 2;
        left = rect.right + gap;
        break;
    }

    setCoords({ top, left });
  }, [position]);

  const toggle = useCallback(() => {
    if (!visible) updatePosition();
    setVisible((v) => !v);
  }, [visible, updatePosition]);

  // Click outside to close
  useEffect(() => {
    if (!visible) return;
    const handler = (e: MouseEvent) => {
      if (
        popoverRef.current && !popoverRef.current.contains(e.target as Node) &&
        triggerRef.current && !triggerRef.current.contains(e.target as Node)
      ) {
        setVisible(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [visible]);

  // Escape to close
  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setVisible(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [visible]);

  const triggerProps = trigger === "click"
    ? { onClick: toggle }
    : {
        onMouseEnter: () => { updatePosition(); setVisible(true); },
        onMouseLeave: () => setVisible(false),
      };

  return (
    <>
      <span ref={triggerRef} className="popover-trigger" {...triggerProps}>
        {children}
      </span>
      {visible &&
        createPortal(
          <div
            ref={popoverRef}
            className={`ui-popover ui-popover-${position}`}
            style={{ top: coords.top, left: coords.left }}
          >
            <div className="ui-popover-content">{content}</div>
          </div>,
          getOverlayRoot()
        )}
    </>
  );
}
