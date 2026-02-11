/**
 * Generic context menu component, portalled to document body.
 */

import { useEffect, useCallback, useRef } from "react";

export interface ContextMenuItem {
  label: string;
  icon?: string;
  action: () => void;
  destructive?: boolean;
  separator?: boolean;
}

interface ContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
}

export function ContextMenu({ x, y, items, onClose }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  // Position clamping to keep menu in viewport
  useEffect(() => {
    if (!menuRef.current) return;
    const rect = menuRef.current.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width - 8;
    const maxY = window.innerHeight - rect.height - 8;
    if (x > maxX) menuRef.current.style.left = `${maxX}px`;
    if (y > maxY) menuRef.current.style.top = `${maxY}px`;
  }, [x, y]);

  // Close on Escape
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleItemClick = useCallback(
    (item: ContextMenuItem) => {
      item.action();
      onClose();
    },
    [onClose]
  );

  return (
    <>
      <div className="context-menu-backdrop" onClick={onClose} />
      <div
        ref={menuRef}
        className="context-menu"
        style={{ left: x, top: y }}
      >
        {items.map((item, i) =>
          item.separator ? (
            <div key={i} className="context-menu-separator" />
          ) : (
            <button
              key={i}
              className={`context-menu-item ${item.destructive ? "destructive" : ""}`}
              onClick={() => handleItemClick(item)}
            >
              {item.icon && <span>{item.icon}</span>}
              <span>{item.label}</span>
            </button>
          )
        )}
      </div>
    </>
  );
}

// =============================================================================
// Hook for managing context menu state
// =============================================================================

import { useState } from "react";

export function useContextMenu() {
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    items: ContextMenuItem[];
  } | null>(null);

  const showContextMenu = useCallback(
    (e: React.MouseEvent, items: ContextMenuItem[]) => {
      e.preventDefault();
      setMenu({ x: e.clientX, y: e.clientY, items });
    },
    []
  );

  const closeContextMenu = useCallback(() => {
    setMenu(null);
  }, []);

  return { menu, showContextMenu, closeContextMenu };
}
