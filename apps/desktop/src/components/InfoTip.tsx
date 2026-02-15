/**
 * Reusable info tooltip component.
 *
 * Small "i" icon that shows an explanation on hover/click/focus.
 * Now renders via portal to #overlay-root to avoid z-index/overflow clipping.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface InfoTipProps {
  text: string;
  position?: "top" | "bottom" | "left" | "right";
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

export function InfoTip({ text, position = "top" }: InfoTipProps) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
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

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (
      triggerRef.current && !triggerRef.current.contains(e.target as Node) &&
      popoverRef.current && !popoverRef.current.contains(e.target as Node)
    ) {
      setVisible(false);
    }
  }, []);

  useEffect(() => {
    if (visible) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [visible, handleClickOutside]);

  const show = useCallback(() => {
    updatePosition();
    setVisible(true);
  }, [updatePosition]);

  return (
    <span className="infotip-wrapper">
      <button
        ref={triggerRef}
        className={`infotip-trigger ${visible ? "active" : ""}`}
        onClick={(e) => {
          e.stopPropagation();
          if (visible) {
            setVisible(false);
          } else {
            show();
          }
        }}
        onMouseEnter={show}
        onMouseLeave={() => setVisible(false)}
        onFocus={show}
        onBlur={() => setVisible(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setVisible(false);
        }}
        aria-label="More information"
        aria-expanded={visible}
      >
        i
      </button>
      {visible &&
        createPortal(
          <div
            ref={popoverRef}
            className={`infotip-popover infotip-${position}`}
            style={{
              position: "fixed",
              top: coords.top,
              left: coords.left,
              zIndex: 2000,
            }}
          >
            <div className="infotip-content">{text}</div>
          </div>,
          getOverlayRoot()
        )}
    </span>
  );
}
