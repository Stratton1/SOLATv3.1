import { useMemo, useState } from "react";
import { CatalogueItem } from "../../lib/engineClient";

type AssetTab = "fx" | "index" | "commodity" | "crypto" | "stock";

interface MarketBrowserProps {
  items: CatalogueItem[];
  currentSymbol: string;
  onSelectSymbol: (symbol: string) => void;
}

const TAB_ORDER: AssetTab[] = ["fx", "index", "commodity", "crypto", "stock"];

const TAB_LABELS: Record<AssetTab, string> = {
  fx: "FX",
  index: "Indices",
  commodity: "Commodities",
  crypto: "Crypto",
  stock: "Shares",
};

export function MarketBrowser({ items, currentSymbol, onSelectSymbol }: MarketBrowserProps) {
  const [activeTab, setActiveTab] = useState<AssetTab>("fx");
  const [search, setSearch] = useState("");

  const byTab = useMemo(() => {
    const grouped: Record<AssetTab, CatalogueItem[]> = {
      fx: [],
      index: [],
      commodity: [],
      crypto: [],
      stock: [],
    };
    for (const item of items) {
      const key = (item.asset_class ?? "").toLowerCase() as AssetTab;
      if (key in grouped) {
        grouped[key].push(item);
      }
    }
    for (const key of TAB_ORDER) {
      grouped[key].sort((a, b) => {
        if (key === "crypto") {
          const scoreA = a.history_score ?? 0;
          const scoreB = b.history_score ?? 0;
          if (scoreA !== scoreB) return scoreB - scoreA;
          const supportedA = a.history_supported ? 1 : 0;
          const supportedB = b.history_supported ? 1 : 0;
          if (supportedA !== supportedB) return supportedB - supportedA;
        }
        return a.symbol.localeCompare(b.symbol);
      });
    }
    return grouped;
  }, [items]);

  const visibleTabs = useMemo(
    () => TAB_ORDER.filter((tab) => byTab[tab].length > 0),
    [byTab]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const source = byTab[activeTab] ?? [];
    if (!q) return source;
    return source.filter(
      (item) =>
        item.symbol.toLowerCase().includes(q) ||
        item.display_name.toLowerCase().includes(q)
    );
  }, [activeTab, byTab, search]);

  return (
    <div className="market-browser">
      <div className="market-browser-tabs">
        {visibleTabs.map((tab) => (
          <button
            key={tab}
            className={`market-tab-btn ${tab === activeTab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>
      <input
        className="market-browser-search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search markets..."
      />
      <div className="market-browser-list">
        {filtered.slice(0, 80).map((item) => {
          const symbolUpper = item.symbol.toUpperCase();
          return (
            <button
              key={item.symbol}
              className={`market-browser-item ${
                currentSymbol.toUpperCase() === symbolUpper ? "active" : ""
              }`}
              onClick={() => onSelectSymbol(symbolUpper)}
            >
              <span>{symbolUpper}</span>
              <span className="item-name">
                {item.display_name}
                {activeTab === "crypto" && typeof item.history_score === "number"
                  ? ` · H${item.history_score.toFixed(0)}`
                  : ""}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
