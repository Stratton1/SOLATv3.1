/**
 * Platform Guide — slide-over panel with documentation sections.
 */

import { useState } from "react";

interface GuideDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

type Section =
  | "getting-started"
  | "tabs"
  | "workflow"
  | "strategies"
  | "risk"
  | "shortcuts"
  | "troubleshooting";

const SECTIONS: Array<{ key: Section; title: string }> = [
  { key: "getting-started", title: "Getting Started" },
  { key: "tabs", title: "Tab Overview" },
  { key: "workflow", title: "Trading Workflow" },
  { key: "strategies", title: "Elite 8 Strategies" },
  { key: "risk", title: "Risk Controls" },
  { key: "shortcuts", title: "Keyboard Shortcuts" },
  { key: "troubleshooting", title: "Troubleshooting" },
];

export function GuideDrawer({ isOpen, onClose }: GuideDrawerProps) {
  const [active, setActive] = useState<Section>("getting-started");

  if (!isOpen) return null;

  return (
    <div className="guide-backdrop" onClick={onClose}>
      <div className="guide-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="guide-header">
          <h2>Platform Guide</h2>
          <button className="guide-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="guide-body">
          <nav className="guide-nav">
            {SECTIONS.map((s) => (
              <button
                key={s.key}
                className={`guide-nav-item ${active === s.key ? "active" : ""}`}
                onClick={() => setActive(s.key)}
              >
                {s.title}
              </button>
            ))}
          </nav>

          <div className="guide-content">
            {active === "getting-started" && <GettingStarted />}
            {active === "tabs" && <TabOverview />}
            {active === "workflow" && <TradingWorkflow />}
            {active === "strategies" && <StrategiesGuide />}
            {active === "risk" && <RiskControls />}
            {active === "shortcuts" && <Shortcuts />}
            {active === "troubleshooting" && <TroubleshootingGuide />}
          </div>
        </div>
      </div>
    </div>
  );
}

function GettingStarted() {
  return (
    <div className="guide-section">
      <h3>Getting Started</h3>
      <ol className="guide-steps">
        <li>
          <strong>Configure credentials</strong> — Copy <code>.env.example</code> to{" "}
          <code>.env</code> in the engine directory. Add your IG API key, username, and password.
        </li>
        <li>
          <strong>Start the engine</strong> — Run <code>./scripts/dev.sh</code> or click
          "Start Engine" in the System tab. The engine binds to <code>127.0.0.1:8765</code>.
        </li>
        <li>
          <strong>Test broker connection</strong> — Go to the System tab and click "Test Connection"
          in the Broker Connectivity card. This authenticates with IG Markets.
        </li>
        <li>
          <strong>Sync market data</strong> — Use "Sync 30d" in the Data Library card to download
          recent OHLCV bars, then "Derive" to build higher timeframes.
        </li>
        <li>
          <strong>Run your first backtest</strong> — Navigate to Backtests and click "New Backtest".
          Select a bot, symbol, and timeframe to evaluate a strategy.
        </li>
      </ol>
    </div>
  );
}

function TabOverview() {
  return (
    <div className="guide-section">
      <h3>Tab Overview</h3>
      <dl className="guide-definitions">
        <dt>Dashboard</dt>
        <dd>Real-time KPIs, mini chart, open positions, watchlist, equity curve, and recent signals.</dd>
        <dt>Charts</dt>
        <dd>Full-screen candlestick workspace with indicator overlays, signal markers, and multi-timeframe support.</dd>
        <dt>Backtests</dt>
        <dd>Run and review strategy backtests. See metrics, per-bot breakdown, trade log, and equity curves.</dd>
        <dt>Optimise</dt>
        <dd>Scheduler for walk-forward optimisation, recommended sets, active allowlist, and proposals.</dd>
        <dt>Blotter</dt>
        <dd>Audit trail of all execution events, fills, and orders with filters and CSV export.</dd>
        <dt>System</dt>
        <dd>Infrastructure health, broker connectivity, risk gates, execution controls, data library, event log, and DEMO setup checklist.</dd>
      </dl>
    </div>
  );
}

function TradingWorkflow() {
  return (
    <div className="guide-section">
      <h3>Trading Workflow</h3>
      <div className="guide-flow">
        <div className="guide-flow-step">
          <span className="guide-flow-num">1</span>
          <div>
            <strong>Sync Data</strong>
            <p>Download latest OHLCV bars from IG, then derive 5m/15m/1h/4h timeframes from 1-minute data.</p>
          </div>
        </div>
        <div className="guide-flow-step">
          <span className="guide-flow-num">2</span>
          <div>
            <strong>Backtest</strong>
            <p>Test strategies against historical data. Review Sharpe ratio, win rate, and drawdown metrics.</p>
          </div>
        </div>
        <div className="guide-flow-step">
          <span className="guide-flow-num">3</span>
          <div>
            <strong>Walk-Forward Optimise</strong>
            <p>Run WFO to find robust parameter sets. Only strategies that perform well out-of-sample are recommended.</p>
          </div>
        </div>
        <div className="guide-flow-step">
          <span className="guide-flow-num">4</span>
          <div>
            <strong>Apply Allowlist</strong>
            <p>Apply recommended bot/symbol/timeframe combos to the trading allowlist.</p>
          </div>
        </div>
        <div className="guide-flow-step">
          <span className="guide-flow-num">5</span>
          <div>
            <strong>Arm &amp; Autopilot</strong>
            <p>Arm the execution engine in DEMO mode, enable Autopilot, and monitor via Dashboard.</p>
          </div>
        </div>
        <div className="guide-flow-step">
          <span className="guide-flow-num">6</span>
          <div>
            <strong>Monitor</strong>
            <p>Watch real-time signals, fills, and PnL. Use the Kill Switch for emergency stops.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function StrategiesGuide() {
  return (
    <div className="guide-section">
      <h3>Elite 8 Strategies</h3>
      <p className="guide-intro">Eight deterministic strategies spanning four categories:</p>
      <dl className="guide-definitions">
        <dt>Trend Following</dt>
        <dd><strong>CloudTwist</strong> — Ichimoku Cloud + MACD crossover confirmation.<br/>
        <strong>TKCrossSniper</strong> — Tenkan/Kijun cross with ADX strength filter.</dd>
        <dt>Momentum</dt>
        <dd><strong>MomentumRider</strong> — RSI + MACD momentum alignment.<br/>
        <strong>StochPop</strong> — Stochastic overbought/oversold reversal.</dd>
        <dt>Reversal</dt>
        <dd><strong>KijunBouncer</strong> — Kijun-sen bounce with volume confirmation.<br/>
        <strong>ReversalHunter</strong> — Multi-indicator reversal detection.</dd>
        <dt>Breakout</dt>
        <dd><strong>BreakoutKing</strong> — Bollinger Band + ATR breakout with volatility filter.<br/>
        <strong>VolSurfer</strong> — Volatility regime-switching strategy.</dd>
      </dl>
    </div>
  );
}

function RiskControls() {
  return (
    <div className="guide-section">
      <h3>Risk Controls</h3>
      <p className="guide-intro">9 pre-trade checks enforced by the Risk Engine:</p>
      <ul className="guide-list">
        <li><strong>Position Size Cap</strong> — Maximum lot size per order</li>
        <li><strong>Concurrent Positions</strong> — Limit on open trades</li>
        <li><strong>Daily Loss Limit</strong> — Stop trading after threshold loss</li>
        <li><strong>Trades/Hour</strong> — Rate limit on order frequency</li>
        <li><strong>Per-Symbol Exposure</strong> — Max position per instrument</li>
        <li><strong>Stop-Loss Required</strong> — Every order must have SL</li>
        <li><strong>Duplicate Check</strong> — Idempotent order submission</li>
        <li><strong>Circuit Breaker</strong> — Consecutive loss threshold</li>
        <li><strong>Size Validator</strong> — Minimum/maximum size bounds</li>
      </ul>
      <h4>Kill Switch</h4>
      <p>Immediately halts all trading and optionally closes open positions. Must be explicitly reset before trading resumes.</p>
      <h4>DEMO vs LIVE</h4>
      <p>Execution defaults to DEMO. LIVE mode requires multi-gate confirmation: LIVE_ENABLE_TOKEN, LIVE_TRADING_ENABLED, and manual arm sequence.</p>
    </div>
  );
}

function Shortcuts() {
  return (
    <div className="guide-section">
      <h3>Keyboard Shortcuts</h3>
      <table className="guide-shortcut-table">
        <tbody>
          <tr><td><kbd>Cmd+1</kbd></td><td>Dashboard</td></tr>
          <tr><td><kbd>Cmd+2</kbd></td><td>Charts</td></tr>
          <tr><td><kbd>Cmd+3</kbd></td><td>Backtests</td></tr>
          <tr><td><kbd>Cmd+4</kbd></td><td>Optimise</td></tr>
          <tr><td><kbd>Cmd+5</kbd></td><td>Blotter</td></tr>
          <tr><td><kbd>Cmd+6</kbd></td><td>System</td></tr>
          <tr><td><kbd>Cmd+K</kbd></td><td>Command Palette</td></tr>
          <tr><td><kbd>Esc</kbd></td><td>Close overlay</td></tr>
        </tbody>
      </table>
    </div>
  );
}

function TroubleshootingGuide() {
  return (
    <div className="guide-section">
      <h3>Troubleshooting</h3>
      <dl className="guide-definitions">
        <dt>Engine Offline</dt>
        <dd>Check the engine process is running on port 8765. Use "Start Engine" in the System tab or run <code>./scripts/dev.sh</code> manually.</dd>
        <dt>IG Connection Failed</dt>
        <dd>Verify credentials in <code>.env</code>. Ensure IG API key is valid and account is not locked. DEMO accounts use <code>demo-api.ig.com</code>.</dd>
        <dt>No Bar Data</dt>
        <dd>Use "Sync 30d" in the Data Library to download historical bars. Then "Derive" to create higher timeframe aggregates from 1-minute data.</dd>
        <dt>Backtest Shows 0 Trades</dt>
        <dd>The selected strategy may not generate signals for that symbol/timeframe combination. Try a different timeframe or check the strategy's required bar count.</dd>
        <dt>Kill Switch Active</dt>
        <dd>The kill switch must be explicitly reset before trading resumes. Go to System &gt; Execution Control and click "Reset Kill Switch".</dd>
      </dl>
    </div>
  );
}
