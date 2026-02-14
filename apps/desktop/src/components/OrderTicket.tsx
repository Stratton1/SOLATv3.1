import { useState, useMemo } from "react";
import { engineClient } from "../lib/engineClient";
import { useToast } from "../context/ToastContext";

interface OrderTicketProps {
  symbol: string;
  price?: number;
  onClose: () => void;
}

export function OrderTicket({ symbol, price, onClose }: OrderTicketProps) {
  const { showToast } = useToast();
  const [direction, setDirection] = useState<"BUY" | "SELL">("BUY");
  const [size, setSize] = useState(1);
  const [type, setType] = useState<"MARKET" | "LIMIT" | "STOP">("MARKET");
  const [limitPrice, setLimitPrice] = useState(price || 0);
  const [sl, setSl] = useState<number | "">("");
  const [tp, setTp] = useState<number | "">("");
  const [riskPct, setRiskPct] = useState<number | "">("");

  // Account for risk calc (mocked for now, should come from context)
  const accountBalance = 10000; 

  const handleRiskCalc = (pct: number) => {
    setRiskPct(pct);
    if (price && typeof sl === "number") {
      const riskAmount = accountBalance * (pct / 100);
      const dist = Math.abs(price - sl);
      if (dist > 0) {
        // Simple lot calc: risk / dist (very rough, ignores pip value)
        // In real app, use engine's risk calculator endpoint
        const rawSize = riskAmount / (dist * 10000); // Assuming 1 lot = $10/pip standard
        setSize(parseFloat(rawSize.toFixed(2)));
      }
    }
  };

  const handleSubmit = async () => {
    try {
      showToast(`Submitting ${direction} ${size} ${symbol}...`, "info");
      await engineClient.placeOrder({
        symbol,
        direction,
        size,
        type,
        limit_price: type !== "MARKET" ? limitPrice : undefined,
        stop_loss: typeof sl === "number" ? sl : undefined,
        take_profit: typeof tp === "number" ? tp : undefined,
        reason: "order_ticket"
      });
      showToast("Order Placed Successfully", "success");
      onClose();
    } catch (err) {
      showToast(`Order Failed: ${err instanceof Error ? err.message : String(err)}`, "error");
    }
  };

  return (
    <div className="order-ticket-overlay">
      <div className="order-ticket">
        <div className="ticket-header">
          <h3>New Order: {symbol}</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="ticket-body">
          <div className="ticket-row direction-toggle">
            <button 
              className={`dir-btn buy ${direction === "BUY" ? "active" : ""}`}
              onClick={() => setDirection("BUY")}
            >
              BUY
            </button>
            <button 
              className={`dir-btn sell ${direction === "SELL" ? "active" : ""}`}
              onClick={() => setDirection("SELL")}
            >
              SELL
            </button>
          </div>

          <div className="ticket-row">
            <label>Type</label>
            <select value={type} onChange={(e) => setType(e.target.value as any)}>
              <option value="MARKET">Market</option>
              <option value="LIMIT">Limit</option>
              <option value="STOP">Stop</option>
            </select>
          </div>

          {type !== "MARKET" && (
            <div className="ticket-row">
              <label>Price</label>
              <input 
                type="number" 
                value={limitPrice} 
                onChange={(e) => setLimitPrice(parseFloat(e.target.value))}
                step="0.00001"
              />
            </div>
          )}

          <div className="ticket-row">
            <label>Size (Lots)</label>
            <div className="input-group">
               <input 
                 type="number" 
                 value={size} 
                 onChange={(e) => setSize(parseFloat(e.target.value))}
                 step="0.01"
               />
            </div>
          </div>

          <div className="ticket-section">
            <h4>Risk Management</h4>
            <div className="risk-presets">
               {[0.5, 1, 2].map(r => (
                 <button key={r} onClick={() => handleRiskCalc(r)}>{r}%</button>
               ))}
            </div>
            
            <div className="ticket-row">
              <label>Stop Loss</label>
              <input 
                type="number" 
                value={sl} 
                onChange={(e) => setSl(parseFloat(e.target.value))}
                placeholder="Price"
                step="0.00001"
              />
            </div>

            <div className="ticket-row">
               <label>Take Profit</label>
               <input 
                 type="number" 
                 value={tp} 
                 onChange={(e) => setTp(parseFloat(e.target.value))}
                 placeholder="Price"
                 step="0.00001"
               />
            </div>
          </div>

          <button className={`submit-btn ${direction.toLowerCase()}`} onClick={handleSubmit}>
            PLACE {direction} ORDER
          </button>
        </div>
      </div>
    </div>
  );
}
