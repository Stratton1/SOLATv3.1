/**
 * IndicatorPopover — dropdown to manage chart indicators (add, toggle, remove).
 */

import { memo, useEffect, useState } from "react";
import { PanelIndicator } from "../../lib/workspace";
import { engineClient } from "../../lib/engineClient";

interface IndicatorPopoverProps {
  indicators: PanelIndicator[];
  onUpdate: (indicators: PanelIndicator[]) => void;
  onClose: () => void;
}

interface AvailableIndicator {
  name: string;
  display: string;
  description: string;
  params: Record<string, { type: string; default: number; min?: number; max?: number }>;
  separate_pane?: boolean;
}

export const IndicatorPopover = memo(function IndicatorPopover({
  indicators,
  onUpdate,
  onClose,
}: IndicatorPopoverProps) {
  const [available, setAvailable] = useState<AvailableIndicator[]>([]);
  const [addType, setAddType] = useState("");
  const [addPeriod, setAddPeriod] = useState(14);

  useEffect(() => {
    engineClient
      .getAvailableIndicators()
      .then((res) => setAvailable(res.indicators as unknown as AvailableIndicator[]))
      .catch(() => {});
  }, []);

  const toggleIndicator = (idx: number) => {
    onUpdate(indicators.map((ind, i) => (i === idx ? { ...ind, enabled: !ind.enabled } : ind)));
  };

  const removeIndicator = (idx: number) => {
    onUpdate(indicators.filter((_, i) => i !== idx));
  };

  const addIndicator = () => {
    if (!addType) return;
    const meta = available.find((a) => a.name === addType);
    const params: Record<string, number> = {};

    if (meta) {
      for (const [key, spec] of Object.entries(meta.params)) {
        if (key === "period" || key === "k_period") {
          params[key] = addPeriod;
        } else {
          params[key] = spec.default;
        }
      }
    }

    onUpdate([...indicators, { type: addType.toUpperCase(), params, enabled: true }]);
    setAddType("");
    setAddPeriod(14);
  };

  const indicatorLabel = (ind: PanelIndicator) => {
    const period = ind.params.period ?? ind.params.k_period;
    return period ? `${ind.type}(${period})` : ind.type;
  };

  return (
    <>
      <div className="dropdown-backdrop" onClick={onClose} />
      <div className="chart-popover">
        <div className="popover-header">
          <span className="popover-title">Indicators</span>
        </div>

        {/* Current indicators */}
        <div className="popover-list">
          {indicators.map((ind, idx) => (
            <div key={idx} className="popover-row">
              <input
                type="checkbox"
                checked={ind.enabled}
                onChange={() => toggleIndicator(idx)}
              />
              <span className="popover-row-label">{indicatorLabel(ind)}</span>
              <button
                className="popover-remove-btn"
                onClick={() => removeIndicator(idx)}
                title="Remove"
              >
                &times;
              </button>
            </div>
          ))}
          {indicators.length === 0 && (
            <div className="popover-empty">No indicators added</div>
          )}
        </div>

        {/* Add new indicator */}
        <div className="popover-add-section">
          <select
            className="popover-select"
            value={addType}
            onChange={(e) => {
              setAddType(e.target.value);
              const meta = available.find((a) => a.name === e.target.value);
              if (meta?.params.period) {
                setAddPeriod(meta.params.period.default);
              }
            }}
          >
            <option value="">Add indicator...</option>
            {available.map((a) => (
              <option key={a.name} value={a.name}>
                {a.display}
              </option>
            ))}
          </select>

          {addType && (() => {
            const meta = available.find((a) => a.name === addType);
            const hasPeriod = meta?.params.period || meta?.params.k_period;
            return hasPeriod ? (
              <input
                type="number"
                className="popover-period-input"
                value={addPeriod}
                onChange={(e) => setAddPeriod(Number(e.target.value))}
                min={2}
                max={200}
              />
            ) : null;
          })()}

          <button
            className="popover-add-btn"
            onClick={addIndicator}
            disabled={!addType}
          >
            Add
          </button>
        </div>
      </div>
    </>
  );
});
