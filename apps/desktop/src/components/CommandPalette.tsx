/**
 * Command Palette — Cmd+K fuzzy search for navigation and actions.
 */

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { searchCommands, Command, GROUP_LABELS } from "../lib/commands";

interface CommandPaletteProps {
  onClose: () => void;
  onNavigate: (path: string) => void;
}

export function CommandPalette({ onClose, onNavigate }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [highlightIdx, setHighlightIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const results = useMemo(() => searchCommands(query), [query]);

  // Reset highlight when results change
  useEffect(() => {
    setHighlightIdx(0);
  }, [results.length]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const executeCommand = useCallback(
    (cmd: Command) => {
      if (cmd.path) {
        onNavigate(cmd.path);
      } else if (cmd.symbol) {
        // Navigate to terminal with symbol
        sessionStorage.setItem(
          "solat_chart_deeplink",
          JSON.stringify({ symbol: cmd.symbol, timeframe: "1h" })
        );
        onNavigate("/terminal");
      }
      onClose();
    },
    [onNavigate, onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightIdx((prev) => Math.min(prev + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightIdx((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" && results.length > 0) {
        e.preventDefault();
        executeCommand(results[highlightIdx]);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [results, highlightIdx, executeCommand, onClose]
  );

  // Scroll highlighted item into view
  useEffect(() => {
    const el = listRef.current?.children[highlightIdx] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightIdx]);

  // Group results for display
  const grouped = useMemo(() => {
    const groups: Array<{ group: string; items: Array<{ cmd: Command; flatIndex: number }> }> = [];
    let flatIndex = 0;
    const seen = new Set<string>();

    for (const cmd of results) {
      if (!seen.has(cmd.group)) {
        seen.add(cmd.group);
        groups.push({ group: cmd.group, items: [] });
      }
      const g = groups.find((g) => g.group === cmd.group)!;
      g.items.push({ cmd, flatIndex });
      flatIndex++;
    }
    return groups;
  }, [results]);

  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div
        className="palette-container"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="palette-input"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a command..."
        />
        <div className="palette-results" ref={listRef}>
          {results.length === 0 ? (
            <div className="palette-empty">No matching commands</div>
          ) : (
            grouped.map(({ group, items }) => (
              <div key={group}>
                <div className="palette-group-label">
                  {GROUP_LABELS[group] ?? group}
                </div>
                {items.map(({ cmd, flatIndex }) => (
                  <div
                    key={cmd.id}
                    className={`palette-item ${flatIndex === highlightIdx ? "highlighted" : ""}`}
                    onClick={() => executeCommand(cmd)}
                    onMouseEnter={() => setHighlightIdx(flatIndex)}
                  >
                    <span className="palette-item-icon">{cmd.icon}</span>
                    <span className="palette-item-label">{cmd.label}</span>
                    {cmd.shortcut && (
                      <span className="palette-item-shortcut">{cmd.shortcut}</span>
                    )}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
