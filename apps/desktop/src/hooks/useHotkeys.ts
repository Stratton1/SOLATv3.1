/**
 * Global keyboard shortcut hook.
 *
 * Usage:
 *   useHotkeys({
 *     "Meta+k": () => openPalette(),
 *     "Meta+1": () => navigate("/"),
 *     "Escape": () => closePalette(),
 *   });
 *
 * Key names follow KeyboardEvent.key (Meta = Cmd on macOS).
 * Shortcuts are suppressed when the user is typing in an input/textarea.
 */

import { useEffect, useRef } from "react";

type KeyMap = Record<string, () => void>;

/** Returns true if focus is in an editable field */
function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

/**
 * Parse a combo like "Meta+k" into {meta, ctrl, shift, alt, key}.
 */
function parseCombo(combo: string) {
  const parts = combo.split("+");
  const key = parts[parts.length - 1].toLowerCase();
  return {
    meta: parts.some((p) => p.toLowerCase() === "meta"),
    ctrl: parts.some((p) => p.toLowerCase() === "ctrl" || p.toLowerCase() === "control"),
    shift: parts.some((p) => p.toLowerCase() === "shift"),
    alt: parts.some((p) => p.toLowerCase() === "alt"),
    key,
  };
}

export function useHotkeys(keymap: KeyMap) {
  const keymapRef = useRef(keymap);
  keymapRef.current = keymap;

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      // Allow Escape even in inputs (for closing modals)
      const isEscape = e.key === "Escape";
      if (!isEscape && isEditableTarget(e.target)) return;

      for (const [combo, action] of Object.entries(keymapRef.current)) {
        const parsed = parseCombo(combo);
        const keyMatch = e.key.toLowerCase() === parsed.key;
        const metaMatch = e.metaKey === parsed.meta;
        const ctrlMatch = e.ctrlKey === parsed.ctrl;
        const shiftMatch = e.shiftKey === parsed.shift;
        const altMatch = e.altKey === parsed.alt;

        if (keyMatch && metaMatch && ctrlMatch && shiftMatch && altMatch) {
          e.preventDefault();
          e.stopPropagation();
          action();
          return;
        }
      }
    }

    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, []);
}
