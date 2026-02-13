# Product Definition - SOLAT v3.1

## Initial Concept
SOLAT (Strategic Opportunistic Leveraged Algorithmic Trading) is a production-grade desktop trading terminal designed for individual algorithmic traders (the developer and friends). It bridges the gap between complex algorithmic engines and user-friendly trading interfaces, specifically integrated with the IG broker.

## Target Audience
- **Primary:** The developer (Joseph).
- **Secondary:** A small group of trusted friends/associates interested in algorithmic traders.

## Core Goals
1.  **Terminal UI Completion:** Finalize the React-based terminal to provide professional-grade visualization of real-time market data, including candlestick charts, technical overlays, and entry/exit signals.
2.  **Live Readiness Hardening:** Transition the system from a reliable backtesting and demo tool to a "Live-Ready" platform by hardening risk management protocols, performance stability, and error recovery.
3.  **Backtesting Integrity & Expansion:** Maintain a deterministic, high-fidelity backtesting environment while expanding its capabilities to support more complex strategy sweeps and realistic market friction.

## Key Features & Milestone Focus
- **Visual Backtest Replay:** Enable traders to visually "walk through" historical trades on the terminal charts, allowing for intuitive verification of strategy logic and signal timing.
- **Demo Trading Success:** Ensure the "DEMO" mode is bulletproof—successfully sending signals to the IG demo environment, managing virtual positions, and accurately reflecting account state without real financial risk.
- **Risk Management Controls:** Implementation of essential safeguards including size caps, position limits, and a robust "Kill Switch" for immediate market exit.
- **High-Performance Data Layer:** Continued optimization of the Parquet-based historical data store for rapid strategy iteration and real-time data aggregation.
