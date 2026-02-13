/**
 * StrategyPopover — dropdown to select which strategies generate signals on the chart.
 */

import { memo, useEffect, useState } from "react";
import { PanelBot } from "../../lib/workspace";
import { StrategyInfo, engineClient } from "../../lib/engineClient";

interface StrategyPopoverProps {
  bots: PanelBot[];
  onUpdate: (bots: PanelBot[]) => void;
  onClose: () => void;
}

export const StrategyPopover = memo(function StrategyPopover({
  bots,
  onUpdate,
  onClose,
}: StrategyPopoverProps) {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);

  useEffect(() => {
    engineClient
      .getAvailableStrategies()
      .then((res) => setStrategies(res.strategies))
      .catch(() => {});
  }, []);

  const enabledSet = new Set(bots.filter((b) => b.enabled).map((b) => b.id));

  const toggleBot = (name: string) => {
    const exists = bots.find((b) => b.id === name);
    if (exists) {
      onUpdate(bots.map((b) => (b.id === name ? { ...b, enabled: !b.enabled } : b)));
    } else {
      onUpdate([...bots, { id: name, enabled: true, params: {} }]);
    }
  };

  const allEnabled = strategies.length > 0 && strategies.every((s) => enabledSet.has(s.name));

  const toggleAll = () => {
    if (allEnabled) {
      onUpdate(bots.map((b) => ({ ...b, enabled: false })));
    } else {
      const newBots = strategies.map((s) => {
        const existing = bots.find((b) => b.id === s.name);
        return existing ? { ...existing, enabled: true } : { id: s.name, enabled: true, params: {} };
      });
      onUpdate(newBots);
    }
  };

  return (
    <>
      <div className="dropdown-backdrop" onClick={onClose} />
      <div className="chart-popover">
        <div className="popover-header">
          <span className="popover-title">Strategies</span>
          <button className="popover-toggle-all" onClick={toggleAll}>
            {allEnabled ? "None" : "All"}
          </button>
        </div>
        <div className="popover-list">
          {strategies.map((s) => (
            <label key={s.name} className="popover-row">
              <input
                type="checkbox"
                checked={enabledSet.has(s.name)}
                onChange={() => toggleBot(s.name)}
              />
              <span className="popover-row-label">{s.name}</span>
              <span className="popover-row-desc">{s.description}</span>
            </label>
          ))}
          {strategies.length === 0 && (
            <div className="popover-empty">Loading strategies...</div>
          )}
        </div>
      </div>
    </>
  );
});
