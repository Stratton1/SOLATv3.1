/**
 * Intro / Home page — two-column layout with brand + getting started tiles.
 * No-scroll discipline: fits within viewport.
 */

import { useNavigate } from "react-router-dom";
import { SummaryBar } from "../components/ui/SummaryBar";
import { useEngineConnection } from "../context/EngineConnectionContext";

const SETUP_STEPS = [
  { num: 1, text: "Sync historical data from your broker", link: "/system", linkText: "System" },
  { num: 2, text: "Review available bots and strategies", link: "/bots", linkText: "Bots" },
  { num: 3, text: "Configure your trading allowlist", link: "/allowlist", linkText: "Allowlist" },
  { num: 4, text: "Backtest strategies on historical data", link: "/backtests", linkText: "Backtests" },
  { num: 5, text: "Optimise and walk-forward validate", link: "/optimise", linkText: "Optimise" },
  { num: 6, text: "Enable DEMO execution or autopilot", link: "/system", linkText: "System" },
];

export function IntroScreen() {
  const navigate = useNavigate();
  const { health } = useEngineConnection();

  return (
    <div className="screen-layout">
      <SummaryBar
        pageId="intro"
        title="Welcome"
        description="SOLAT is your algorithmic trading terminal. Start here to learn the platform workflow."
        chips={[
          { label: "Engine", value: health?.status === "healthy" ? "Online" : "Offline",
            variant: health?.status === "healthy" ? "success" : "danger" },
          { label: "Version", value: health?.version ?? "\u2014", variant: "default" },
        ]}
      />

      <div className="screen-content">
        <div className="intro-container">
          {/* Left column: brand */}
          <div className="intro-left">
            <img src="/image_logo.png" alt="SOLAT" className="intro-logo" />
            <h1 className="intro-title">SOLAT Trading Terminal</h1>
            <p className="intro-tagline">
              Systematic Optimisation &amp; Learning for Algorithmic Trading
            </p>
            <p className="intro-description">
              A desktop terminal for systematic FX trading with Ichimoku-based strategies,
              backtesting, walk-forward validation, and automated execution.
            </p>

            <div className="intro-disclaimer">
              <strong>Safety First:</strong> Always start in DEMO mode. SOLAT connects to IG Markets &mdash; LIVE
              trading requires explicit multi-gate confirmation and carries real financial risk. Paper trade
              and backtest thoroughly before enabling any live execution.
            </div>
          </div>

          {/* Right column: getting started */}
          <div className="intro-right">
            <h3 className="intro-section-title">Getting Started</h3>
            <div className="intro-tiles">
              {SETUP_STEPS.map((step) => (
                <button
                  key={step.num}
                  className="intro-tile"
                  onClick={() => navigate(step.link)}
                >
                  <span className="intro-tile-num">{step.num}</span>
                  <span className="intro-tile-text">{step.text}</span>
                  <span className="intro-tile-dest">{step.linkText} &rarr;</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
