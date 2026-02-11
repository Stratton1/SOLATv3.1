/**
 * Reusable info tooltip component.
 *
 * Small "i" icon that shows an explanation on hover/click/focus.
 * Used throughout the UI to provide contextual help.
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface InfoTipProps {
  text: string;
  position?: "top" | "bottom" | "left" | "right";
}

export function InfoTip({ text, position = "top" }: InfoTipProps) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (ref.current && !ref.current.contains(e.target as Node)) {
      setVisible(false);
    }
  }, []);

  useEffect(() => {
    if (visible) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [visible, handleClickOutside]);

  return (
    <div className="infotip-wrapper" ref={ref}>
      <button
        className={`infotip-trigger ${visible ? "active" : ""}`}
        onClick={(e) => {
          e.stopPropagation();
          setVisible((v) => !v);
        }}
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onFocus={() => setVisible(true)}
        onBlur={() => setVisible(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setVisible(false);
        }}
        aria-label="More information"
        aria-expanded={visible}
      >
        i
      </button>
      {visible && (
        <div className={`infotip-popover infotip-${position}`}>
          <div className="infotip-content">{text}</div>
        </div>
      )}
    </div>
  );
}
