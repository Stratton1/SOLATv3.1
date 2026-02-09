/**
 * Strategy configuration drawer.
 *
 * Provides:
 * - Bot enable/disable toggles
 * - Parameter editing per bot
 * - Preset management
 * - Allowlist configuration (synced to engine)
 * - Risk settings display
 */

import { useState, useCallback, useMemo } from "react";
import {
  ELITE_8_BOTS,
  CATEGORIES,
  BotMeta,
  BotParam,
  getBotDefaultParams,
} from "../../lib/elite8Meta";
import { useWorkspace } from "../../hooks/useWorkspace";
import { useCatalogue } from "../../hooks/useCatalogue";
import { useAllowlist } from "../../hooks/useAllowlist";
import { useExecutionStatus } from "../../hooks/useExecutionStatus";
import { PanelBot } from "../../lib/workspace";

// =============================================================================
// Types
// =============================================================================

interface StrategyDrawerProps {
  onClose: () => void;
}

type Tab = "bots" | "presets" | "allowlist" | "risk";

interface Preset {
  id: string;
  name: string;
  bots: PanelBot[];
  createdAt: string;
}

const PRESET_STORAGE_KEY = "solat_strategy_presets";

// Allowlist preset groups
const ALLOWLIST_PRESETS: Record<string, string[]> = {
  "Major FX": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD"],
  "Minor FX": ["EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD"],
  "Indices": ["US500", "UK100", "DE40", "JP225", "AU200"],
  "Commodities": ["XAUUSD", "XAGUSD", "USOIL", "UKOIL"],
};

// =============================================================================
// Component
// =============================================================================

export function StrategyDrawer({ onClose }: StrategyDrawerProps) {
  const { workspace, updatePanel } = useWorkspace();
  const [activeTab, setActiveTab] = useState<Tab>("bots");
  const [selectedPanelId, setSelectedPanelId] = useState<string>(
    workspace.panels[0]?.id ?? ""
  );

  // Load presets from localStorage
  const [presets, setPresets] = useState<Preset[]>(() => {
    const stored = localStorage.getItem(PRESET_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  });

  // Get current panel's bots
  const currentPanel = useMemo(
    () => workspace.panels.find((p) => p.id === selectedPanelId),
    [workspace.panels, selectedPanelId]
  );

  const panelBots = useMemo(
    () => currentPanel?.bots ?? [],
    [currentPanel?.bots]
  );

  // Get bot enabled state
  const isBotEnabled = useCallback(
    (botId: string) => panelBots.some((b) => b.id === botId && b.enabled),
    [panelBots]
  );

  // Get bot params
  const getBotParams = useCallback(
    (botId: string) => {
      const bot = panelBots.find((b) => b.id === botId);
      return bot?.params ?? getBotDefaultParams(botId);
    },
    [panelBots]
  );

  // Toggle bot
  const toggleBot = useCallback(
    (botId: string) => {
      if (!currentPanel) return;

      const existingBot = panelBots.find((b) => b.id === botId);
      let newBots: PanelBot[];

      if (existingBot) {
        newBots = panelBots.map((b) =>
          b.id === botId ? { ...b, enabled: !b.enabled } : b
        );
      } else {
        newBots = [
          ...panelBots,
          { id: botId, enabled: true, params: getBotDefaultParams(botId) },
        ];
      }

      updatePanel(selectedPanelId, { bots: newBots });
    },
    [currentPanel, panelBots, selectedPanelId, updatePanel]
  );

  // Update bot param
  const updateBotParam = useCallback(
    (botId: string, paramName: string, value: number | string | boolean) => {
      if (!currentPanel) return;

      const existingBot = panelBots.find((b) => b.id === botId);
      let newBots: PanelBot[];

      if (existingBot) {
        newBots = panelBots.map((b) =>
          b.id === botId
            ? { ...b, params: { ...b.params, [paramName]: value } }
            : b
        );
      } else {
        newBots = [
          ...panelBots,
          {
            id: botId,
            enabled: false,
            params: { ...getBotDefaultParams(botId), [paramName]: value },
          },
        ];
      }

      updatePanel(selectedPanelId, { bots: newBots });
    },
    [currentPanel, panelBots, selectedPanelId, updatePanel]
  );

  // Apply to all panels
  const applyToAllPanels = useCallback(() => {
    for (const panel of workspace.panels) {
      if (panel.id !== selectedPanelId) {
        updatePanel(panel.id, { bots: [...panelBots] });
      }
    }
  }, [workspace.panels, selectedPanelId, panelBots, updatePanel]);

  // Save preset
  const savePreset = useCallback(() => {
    const name = prompt("Preset name:");
    if (!name) return;

    const newPreset: Preset = {
      id: Math.random().toString(36).substring(2, 10),
      name,
      bots: [...panelBots],
      createdAt: new Date().toISOString(),
    };

    const newPresets = [...presets, newPreset];
    setPresets(newPresets);
    localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(newPresets));
  }, [panelBots, presets]);

  // Load preset
  const loadPreset = useCallback(
    (preset: Preset) => {
      updatePanel(selectedPanelId, { bots: [...preset.bots] });
    },
    [selectedPanelId, updatePanel]
  );

  // Delete preset
  const deletePreset = useCallback(
    (presetId: string) => {
      const newPresets = presets.filter((p) => p.id !== presetId);
      setPresets(newPresets);
      localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(newPresets));
    },
    [presets]
  );

  // Export preset JSON
  const exportPresets = useCallback(() => {
    const json = JSON.stringify(presets, null, 2);
    navigator.clipboard.writeText(json);
  }, [presets]);

  // Import preset JSON
  const importPresets = useCallback(() => {
    const json = prompt("Paste preset JSON:");
    if (!json) return;

    try {
      const imported = JSON.parse(json) as Preset[];
      const merged = [...presets, ...imported];
      setPresets(merged);
      localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(merged));
    } catch {
      // Invalid JSON
    }
  }, [presets]);

  return (
    <div className="strategy-drawer">
      <div className="drawer-header">
        <h2>Strategy Configuration</h2>
        <button className="drawer-close" onClick={onClose}>
          ×
        </button>
      </div>

      {/* Tabs */}
      <div className="drawer-tabs">
        <button
          className={`drawer-tab ${activeTab === "bots" ? "active" : ""}`}
          onClick={() => setActiveTab("bots")}
        >
          Bots
        </button>
        <button
          className={`drawer-tab ${activeTab === "presets" ? "active" : ""}`}
          onClick={() => setActiveTab("presets")}
        >
          Presets
        </button>
        <button
          className={`drawer-tab ${activeTab === "allowlist" ? "active" : ""}`}
          onClick={() => setActiveTab("allowlist")}
        >
          Allowlist
        </button>
        <button
          className={`drawer-tab ${activeTab === "risk" ? "active" : ""}`}
          onClick={() => setActiveTab("risk")}
        >
          Risk
        </button>
      </div>

      {/* Content */}
      <div className="drawer-content">
        {activeTab === "bots" && (
          <BotsTab
            panels={workspace.panels}
            selectedPanelId={selectedPanelId}
            onSelectPanel={setSelectedPanelId}
            isBotEnabled={isBotEnabled}
            getBotParams={getBotParams}
            onToggleBot={toggleBot}
            onUpdateParam={updateBotParam}
            onApplyToAll={applyToAllPanels}
          />
        )}

        {activeTab === "presets" && (
          <PresetsTab
            presets={presets}
            onSave={savePreset}
            onLoad={loadPreset}
            onDelete={deletePreset}
            onExport={exportPresets}
            onImport={importPresets}
          />
        )}

        {activeTab === "allowlist" && <AllowlistTab />}

        {activeTab === "risk" && <RiskTab />}
      </div>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

interface BotsTabProps {
  panels: { id: string; symbol: string }[];
  selectedPanelId: string;
  onSelectPanel: (id: string) => void;
  isBotEnabled: (botId: string) => boolean;
  getBotParams: (botId: string) => Record<string, number | string | boolean>;
  onToggleBot: (botId: string) => void;
  onUpdateParam: (
    botId: string,
    paramName: string,
    value: number | string | boolean
  ) => void;
  onApplyToAll: () => void;
}

function BotsTab({
  panels,
  selectedPanelId,
  onSelectPanel,
  isBotEnabled,
  getBotParams,
  onToggleBot,
  onUpdateParam,
  onApplyToAll,
}: BotsTabProps) {
  const [expandedBot, setExpandedBot] = useState<string | null>(null);

  return (
    <div className="bots-tab">
      {/* Panel Selector */}
      <div className="panel-selector">
        <label>Apply to panel:</label>
        <select
          value={selectedPanelId}
          onChange={(e) => onSelectPanel(e.target.value)}
        >
          {panels.map((p, i) => (
            <option key={p.id} value={p.id}>
              Panel {i + 1}: {p.symbol}
            </option>
          ))}
        </select>
        <button className="apply-all-btn" onClick={onApplyToAll}>
          Apply to All
        </button>
      </div>

      {/* Bot List */}
      <div className="bot-list">
        {ELITE_8_BOTS.map((bot) => (
          <BotCard
            key={bot.id}
            bot={bot}
            enabled={isBotEnabled(bot.id)}
            params={getBotParams(bot.id)}
            expanded={expandedBot === bot.id}
            onToggle={() => onToggleBot(bot.id)}
            onExpand={() =>
              setExpandedBot(expandedBot === bot.id ? null : bot.id)
            }
            onUpdateParam={(name, value) => onUpdateParam(bot.id, name, value)}
          />
        ))}
      </div>
    </div>
  );
}

interface BotCardProps {
  bot: BotMeta;
  enabled: boolean;
  params: Record<string, number | string | boolean>;
  expanded: boolean;
  onToggle: () => void;
  onExpand: () => void;
  onUpdateParam: (name: string, value: number | string | boolean) => void;
}

function BotCard({
  bot,
  enabled,
  params,
  expanded,
  onToggle,
  onExpand,
  onUpdateParam,
}: BotCardProps) {
  const category = CATEGORIES[bot.category];

  return (
    <div className={`bot-card ${enabled ? "enabled" : ""}`}>
      <div className="bot-card-header" onClick={onExpand}>
        <div className="bot-info">
          <span
            className="bot-category-badge"
            style={{ backgroundColor: category.color }}
          >
            {category.label}
          </span>
          <span className="bot-name">{bot.name}</span>
        </div>
        <div className="bot-controls">
          <span className="bot-warmup">{bot.warmupBars} bars</span>
          <button
            className={`bot-toggle ${enabled ? "on" : "off"}`}
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
          >
            {enabled ? "ON" : "OFF"}
          </button>
          <span className="expand-icon">{expanded ? "▼" : "▶"}</span>
        </div>
      </div>

      <p className="bot-description">{bot.description}</p>

      {expanded && bot.params.length > 0 && (
        <div className="bot-params">
          {bot.params.map((param) => (
            <ParamInput
              key={param.name}
              param={param}
              value={params[param.name] ?? param.default}
              onChange={(value) => onUpdateParam(param.name, value)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface ParamInputProps {
  param: BotParam;
  value: number | string | boolean;
  onChange: (value: number | string | boolean) => void;
}

function ParamInput({ param, value, onChange }: ParamInputProps) {
  if (param.type === "boolean") {
    return (
      <div className="param-row">
        <label>{param.description}</label>
        <input
          type="checkbox"
          checked={value as boolean}
          onChange={(e) => onChange(e.target.checked)}
        />
      </div>
    );
  }

  if (param.type === "select" && param.options) {
    return (
      <div className="param-row">
        <label>{param.description}</label>
        <select
          value={value as string}
          onChange={(e) => onChange(e.target.value)}
        >
          {param.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  // Number input
  return (
    <div className="param-row">
      <label>{param.description}</label>
      <input
        type="number"
        value={value as number}
        min={param.min}
        max={param.max}
        step={param.step}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
    </div>
  );
}

interface PresetsTabProps {
  presets: Preset[];
  onSave: () => void;
  onLoad: (preset: Preset) => void;
  onDelete: (id: string) => void;
  onExport: () => void;
  onImport: () => void;
}

function PresetsTab({
  presets,
  onSave,
  onLoad,
  onDelete,
  onExport,
  onImport,
}: PresetsTabProps) {
  return (
    <div className="presets-tab">
      <div className="presets-actions">
        <button onClick={onSave}>Save Current</button>
        <button onClick={onExport}>Export</button>
        <button onClick={onImport}>Import</button>
      </div>

      <div className="preset-list">
        {presets.length === 0 ? (
          <p className="no-presets">No saved presets. Save your current bot configuration as a preset.</p>
        ) : (
          presets.map((preset) => (
            <div key={preset.id} className="preset-item">
              <div className="preset-info">
                <span className="preset-name">{preset.name}</span>
                <span className="preset-date">
                  {new Date(preset.createdAt).toLocaleDateString()}
                </span>
              </div>
              <div className="preset-actions">
                <button onClick={() => onLoad(preset)}>Load</button>
                <button className="danger" onClick={() => onDelete(preset.id)}>
                  Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function AllowlistTab() {
  const { enrichedItems } = useCatalogue();
  const {
    allowlist,
    isLoading,
    error,
    addSymbol,
    removeSymbol,
    setAllowlist,
  } = useAllowlist();

  const [search, setSearch] = useState("");

  // Filter catalogue items not already in allowlist
  const availableSymbols = useMemo(() => {
    const query = search.toLowerCase();
    return enrichedItems
      .filter(
        (item) =>
          !allowlist.includes(item.symbol) &&
          (item.symbol.toLowerCase().includes(query) ||
            item.display_name.toLowerCase().includes(query))
      )
      .slice(0, 10);
  }, [enrichedItems, allowlist, search]);

  const handleAddPreset = useCallback(
    (presetSymbols: string[]) => {
      const merged = [...new Set([...allowlist, ...presetSymbols])];
      setAllowlist(merged).catch(console.error);
    },
    [allowlist, setAllowlist]
  );

  return (
    <div className="allowlist-tab">
      <p className="allowlist-description">
        Only allowlisted symbols receive orders when execution is armed. The engine
        rejects signals for non-allowlisted symbols.
      </p>

      {error && <p className="allowlist-error">{error}</p>}

      {/* Quick presets */}
      <div className="allowlist-presets">
        <span className="allowlist-presets-label">Quick add:</span>
        {Object.entries(ALLOWLIST_PRESETS).map(([name, symbols]) => (
          <button
            key={name}
            className="allowlist-preset-btn"
            onClick={() => handleAddPreset(symbols)}
            title={symbols.join(", ")}
          >
            {name}
          </button>
        ))}
      </div>

      {/* Search add */}
      <div className="allowlist-add">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search catalogue..."
          className="allowlist-search"
        />
      </div>

      {/* Search results */}
      {search && availableSymbols.length > 0 && (
        <div className="allowlist-search-results">
          {availableSymbols.map((item) => (
            <button
              key={item.symbol}
              className="allowlist-search-item"
              onClick={() => {
                addSymbol(item.symbol).catch(console.error);
                setSearch("");
              }}
            >
              <span className="search-item-symbol">{item.symbol}</span>
              <span className="search-item-name">{item.display_name}</span>
              <span className="search-item-add">+</span>
            </button>
          ))}
        </div>
      )}

      {/* Current allowlist */}
      <div className="allowlist-items">
        {isLoading ? (
          <p className="allowlist-loading">Loading...</p>
        ) : allowlist.length === 0 ? (
          <p className="allowlist-empty">
            No symbols allowlisted. Use the search above or quick add presets.
          </p>
        ) : (
          allowlist.map((symbol) => (
            <div key={symbol} className="allowlist-item">
              <span className="allowlist-item-symbol">{symbol}</span>
              <button
                className="allowlist-item-remove"
                onClick={() => removeSymbol(symbol).catch(console.error)}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>

      <div className="allowlist-count">
        {allowlist.length} symbol{allowlist.length !== 1 ? "s" : ""} allowlisted
      </div>
    </div>
  );
}

function RiskTab() {
  const { status } = useExecutionStatus();

  return (
    <div className="risk-tab">
      <p className="risk-description">
        Execution risk parameters. Changes are made via the engine configuration.
      </p>

      <div className="risk-settings">
        <div className="risk-row">
          <span className="risk-label">Mode</span>
          <span className="risk-value">{status?.mode ?? "—"}</span>
        </div>
        <div className="risk-row">
          <span className="risk-label">Armed</span>
          <span className={`risk-value ${status?.armed ? "risk-active" : ""}`}>
            {status?.armed ? "YES" : "NO"}
          </span>
        </div>
        <div className="risk-row">
          <span className="risk-label">Kill Switch</span>
          <span className={`risk-value ${status?.kill_switch_active ? "risk-danger" : ""}`}>
            {status?.kill_switch_active ? "ACTIVE" : "Off"}
          </span>
        </div>
        <div className="risk-row">
          <span className="risk-label">Open Positions</span>
          <span className="risk-value">{status?.open_position_count ?? 0}</span>
        </div>
        <div className="risk-row">
          <span className="risk-label">Daily PnL</span>
          <span className={`risk-value ${(status?.realized_pnl_today ?? 0) < 0 ? "risk-danger" : "risk-positive"}`}>
            {status?.realized_pnl_today?.toFixed(2) ?? "0.00"}
          </span>
        </div>
        <div className="risk-row">
          <span className="risk-label">Trades/Hour</span>
          <span className="risk-value">{status?.trades_this_hour ?? 0}</span>
        </div>
        <div className="risk-row">
          <span className="risk-label">Account</span>
          <span className="risk-value">{status?.account_id ?? "—"}</span>
        </div>
      </div>

      <p className="risk-note">
        Risk limits are configured in the engine .env file. Use the Status page for
        full execution controls.
      </p>
    </div>
  );
}
