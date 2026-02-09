"""
Backtest Engine V1 - Deterministic bar-driven backtesting.

Main orchestration for running backtests with:
- Multi-symbol support (sequential in v1)
- Strategy signal generation
- Risk gating
- Order execution via BrokerSim
- Portfolio tracking
- Artefact generation
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from solat_engine.backtest.broker_sim import BrokerSim
from solat_engine.backtest.metrics import compute_metrics_summary
from solat_engine.backtest.models import (
    BacktestRequest,
    BacktestResult,
    BotResult,
    OrderAction,
    OrderRecord,
    PositionSide,
    TradeRecord,
)
from solat_engine.backtest.portfolio import Portfolio
from solat_engine.backtest.sizing import (
    calculate_position_size,
    check_risk_limits,
)
from solat_engine.data.models import SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger
from solat_engine.strategies.elite8 import (
    BarData,
    Elite8BaseStrategy,
    Elite8StrategyFactory,
)

logger = get_logger(__name__)

ENGINE_VERSION = "1.0.0"


class BacktestEngineV1:
    """
    Deterministic bar-driven backtest engine.

    Runs strategies on historical bars, simulating execution with
    configurable spread/slippage/fees.
    """

    def __init__(
        self,
        parquet_store: ParquetStore,
        artefacts_dir: Path,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        """
        Initialize backtest engine.

        Args:
            parquet_store: Store for reading historical bars
            artefacts_dir: Directory for output artefacts
            progress_callback: Optional callback for progress events
        """
        self._store = parquet_store
        self._artefacts_dir = artefacts_dir
        self._progress_callback = progress_callback

        # State
        self._portfolio: Portfolio | None = None
        self._broker: BrokerSim | None = None
        self._strategies: dict[str, Elite8BaseStrategy] = {}
        self._all_orders: list[OrderRecord] = []
        self._all_trades: list[TradeRecord] = []
        self._warnings: list[str] = []

    def run(self, request: BacktestRequest) -> BacktestResult:
        """
        Run backtest with given request.

        Args:
            request: Backtest configuration

        Returns:
            BacktestResult with metrics and artefact paths
        """
        run_id = str(uuid4())[:8]
        started_at = datetime.now(UTC)

        logger.info(
            "Starting backtest run_id=%s: %d bots, %d symbols, %s to %s",
            run_id,
            len(request.bots),
            len(request.symbols),
            request.start.isoformat(),
            request.end.isoformat(),
        )

        self._emit_progress({
            "stage": "starting",
            "run_id": run_id,
            "message": f"Starting backtest with {len(request.bots)} bots",
        })

        # Initialize components
        self._portfolio = Portfolio(initial_cash=request.initial_cash)
        self._broker = BrokerSim(
            spread_config=request.spread,
            slippage_config=request.slippage,
            fee_config=request.fees,
        )
        self._strategies = {}
        self._all_orders = []
        self._all_trades = []
        self._warnings = []

        # Load strategies
        for bot_name in request.bots:
            try:
                strategy = Elite8StrategyFactory.create(bot_name, warmup_bars=request.warmup_bars)
                self._strategies[bot_name] = strategy
            except ValueError as e:
                self._warnings.append(f"Failed to load bot {bot_name}: {e}")
                logger.warning("Failed to load bot %s: %s", bot_name, e)

        if not self._strategies:
            return BacktestResult(
                run_id=run_id,
                ok=False,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                request=request,
                errors=["No valid bots loaded"],
                warnings=self._warnings,
                engine_version=ENGINE_VERSION,
            )

        # Parse timeframe
        try:
            timeframe = SupportedTimeframe(request.timeframe)
        except ValueError:
            return BacktestResult(
                run_id=run_id,
                ok=False,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                request=request,
                errors=[f"Invalid timeframe: {request.timeframe}"],
                engine_version=ENGINE_VERSION,
            )

        # Run backtest loop for each symbol
        total_symbols = len(request.symbols)
        for sym_idx, symbol in enumerate(request.symbols):
            self._emit_progress({
                "stage": "processing",
                "run_id": run_id,
                "symbol": symbol,
                "done": sym_idx,
                "total": total_symbols,
                "message": f"Processing {symbol}",
            })

            self._run_symbol(
                symbol=symbol,
                timeframe=timeframe,
                start=request.start,
                end=request.end,
                request=request,
            )

        # Compute per-bot results
        per_bot_results = self._compute_per_bot_results(request)

        # Compute combined metrics
        combined_metrics = compute_metrics_summary(
            equity_curve=self._portfolio.equity_curve,
            trades=self._all_trades,
            initial_cash=request.initial_cash,
        )

        # Write artefacts
        artefact_paths = self._write_artefacts(run_id, request, per_bot_results, combined_metrics)

        self._emit_progress({
            "stage": "completed",
            "run_id": run_id,
            "message": f"Backtest completed: {len(self._all_trades)} trades",
        })

        completed_at = datetime.now(UTC)

        logger.info(
            "Backtest completed run_id=%s: %d trades, Sharpe=%.2f, MaxDD=%.2f%%",
            run_id,
            len(self._all_trades),
            combined_metrics.sharpe_ratio,
            combined_metrics.max_drawdown_pct * 100,
        )

        return BacktestResult(
            run_id=run_id,
            ok=True,
            started_at=started_at,
            completed_at=completed_at,
            request=request,
            per_bot_results=per_bot_results,
            combined_metrics=combined_metrics,
            artefact_paths=artefact_paths,
            warnings=self._warnings + self._broker.get_warnings(),
            engine_version=ENGINE_VERSION,
        )

    def _run_symbol(
        self,
        symbol: str,
        timeframe: SupportedTimeframe,
        start: datetime,
        end: datetime,
        request: BacktestRequest,
    ) -> None:
        """Run backtest for a single symbol."""
        # Load bars
        bars = self._store.read_bars(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )

        if not bars:
            self._warnings.append(f"No bars found for {symbol}/{timeframe.value}")
            logger.warning("No bars found for %s/%s", symbol, timeframe.value)
            return

        if len(bars) < request.warmup_bars:
            self._warnings.append(
                f"Insufficient bars for {symbol}: {len(bars)} < {request.warmup_bars}"
            )
            logger.warning(
                "Insufficient bars for %s: %d < %d",
                symbol,
                len(bars),
                request.warmup_bars,
            )
            return

        logger.debug("Loaded %d bars for %s", len(bars), symbol)

        # Convert to BarData
        bar_data = [
            BarData(
                timestamp=b.timestamp_utc,
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
            for b in bars
        ]

        # Run bar loop
        for i in range(request.warmup_bars, len(bar_data)):
            self._process_bar(
                symbol=symbol,
                bar_data=bar_data[: i + 1],  # Bars up to and including current
                current_bar=bar_data[i],
                request=request,
            )

    def _process_bar(
        self,
        symbol: str,
        bar_data: list[BarData],
        current_bar: BarData,
        request: BacktestRequest,
    ) -> None:
        """Process a single bar for all strategies."""
        assert self._portfolio is not None
        assert self._broker is not None

        timestamp = current_bar.timestamp
        current_price = current_bar.close

        # Update market prices
        self._portfolio.update_prices({symbol: current_price})

        # Check SL/TP exits
        exit_trades = self._portfolio.check_exits(
            timestamp=timestamp,
            prices={symbol: current_price},
            fees_per_trade=self._broker.fee_config.per_trade_flat,
        )
        self._all_trades.extend(exit_trades)

        # Increment bars held for open positions
        self._portfolio.increment_bars_held()

        # Run each strategy
        for bot_name, strategy in self._strategies.items():
            self._run_strategy_on_bar(
                symbol=symbol,
                bot_name=bot_name,
                strategy=strategy,
                bar_data=bar_data,
                current_bar=current_bar,
                request=request,
            )

        # Record equity point
        self._portfolio.record_equity_point(timestamp)

    def _run_strategy_on_bar(
        self,
        symbol: str,
        bot_name: str,
        strategy: Elite8BaseStrategy,
        bar_data: list[BarData],
        current_bar: BarData,
        request: BacktestRequest,
    ) -> None:
        """Run a single strategy on current bar."""
        assert self._portfolio is not None
        assert self._broker is not None

        timestamp = current_bar.timestamp
        current_price = current_bar.close

        # Get current position for this bot/symbol
        position = self._portfolio.get_position(symbol, bot_name)
        current_position_side: str | None = None
        if position:
            current_position_side = position.side.value

        # Generate signal
        signal = strategy.generate_signal(bar_data, current_position_side)

        if signal.is_hold:
            return

        # Handle exit signals
        if position and signal.direction in ("SELL", "BUY"):
            # Check if this is a close signal (opposite direction)
            should_close = (
                (position.is_long and signal.is_sell)
                or (position.is_short and signal.is_buy)
            )

            if should_close:
                # Close the position
                action = OrderAction.CLOSE_LONG if position.is_long else OrderAction.CLOSE_SHORT

                order = self._broker.execute_order(
                    symbol=symbol,
                    bot=bot_name,
                    action=action,
                    size=position.size,
                    bar_close=current_price,
                    timestamp=timestamp,
                )
                self._all_orders.append(order)

                if order.price_filled:
                    trade = self._portfolio.close_position(
                        symbol=symbol,
                        bot=bot_name,
                        exit_price=order.price_filled,
                        exit_time=timestamp,
                        exit_reason="signal",
                        fees=order.fees_applied,
                    )
                    if trade:
                        self._all_trades.append(trade)
                return

        # Handle entry signals (no existing position)
        if not position and signal.is_entry:
            # Calculate position size
            size_result = calculate_position_size(
                signal=signal,
                equity=self._portfolio.equity,
                current_price=current_price,
                risk_config=request.risk,
            )

            if not size_result.is_valid:
                self._warnings.append(
                    f"Size calculation failed for {symbol}/{bot_name}: {size_result.rejection_reason}"
                )
                return

            # Check risk limits
            is_allowed, rejection = check_risk_limits(
                symbol=symbol,
                proposed_size=size_result.size,
                current_price=current_price,
                equity=self._portfolio.equity,
                current_position_count=self._portfolio.position_count,
                current_symbol_exposure=self._portfolio.get_symbol_exposure(symbol),
                current_total_exposure=self._portfolio.total_exposure,
                risk_config=request.risk,
            )

            if not is_allowed:
                logger.debug("Risk limit: %s %s - %s", symbol, bot_name, rejection)
                return

            # Execute entry order
            action = OrderAction.BUY if signal.is_buy else OrderAction.SELL

            order = self._broker.execute_order(
                symbol=symbol,
                bot=bot_name,
                action=action,
                size=size_result.size,
                bar_close=current_price,
                timestamp=timestamp,
            )
            self._all_orders.append(order)

            if order.price_filled:
                side = PositionSide.LONG if signal.is_buy else PositionSide.SHORT

                self._portfolio.open_position(
                    symbol=symbol,
                    bot=bot_name,
                    side=side,
                    size=size_result.size,
                    entry_price=order.price_filled,
                    entry_time=timestamp,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

    def _compute_per_bot_results(self, request: BacktestRequest) -> list[BotResult]:
        """Compute results per bot."""
        assert self._portfolio is not None

        results = []
        for bot_name in request.bots:
            if bot_name not in self._strategies:
                continue

            # Filter trades for this bot
            bot_trades = [t for t in self._all_trades if t.bot == bot_name]
            bot_orders = [o for o in self._all_orders if o.bot == bot_name]
            symbols_traded = list({t.symbol for t in bot_trades})

            # Compute metrics
            metrics = compute_metrics_summary(
                equity_curve=self._portfolio.equity_curve,
                trades=bot_trades,
                initial_cash=request.initial_cash,
                bot=bot_name,
            )

            results.append(BotResult(
                bot=bot_name,
                symbols_traded=symbols_traded,
                metrics=metrics,
                trades_count=len(bot_trades),
                orders_count=len(bot_orders),
            ))

        return results

    def _write_artefacts(
        self,
        run_id: str,
        request: BacktestRequest,
        per_bot_results: list[BotResult],
        combined_metrics: Any,
    ) -> dict[str, str]:
        """Write all artefacts to disk."""
        assert self._portfolio is not None
        assert self._broker is not None

        run_dir = self._artefacts_dir / "backtests" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        artefact_paths: dict[str, str] = {}

        # Manifest
        manifest = {
            "run_id": run_id,
            "engine_version": ENGINE_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "request": {
                "symbols": request.symbols,
                "timeframe": request.timeframe,
                "start": request.start.isoformat(),
                "end": request.end.isoformat(),
                "bots": request.bots,
                "initial_cash": request.initial_cash,
            },
            "data_summary": {
                "total_bars_processed": len(self._portfolio.equity_curve),
                "symbols_count": len(request.symbols),
            },
        }
        manifest_path = run_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)
        artefact_paths["manifest"] = str(manifest_path.relative_to(self._artefacts_dir))

        # Equity curve
        if self._portfolio.equity_curve:
            equity_df = pd.DataFrame([
                {
                    "timestamp": p.timestamp,
                    "equity": p.equity,
                    "cash": p.cash,
                    "unrealized_pnl": p.unrealized_pnl,
                    "realized_pnl": p.realized_pnl,
                    "drawdown": p.drawdown,
                    "drawdown_pct": p.drawdown_pct,
                    "high_water_mark": p.high_water_mark,
                }
                for p in self._portfolio.equity_curve
            ])
            equity_path = run_dir / "equity_curve.parquet"
            equity_df.to_parquet(equity_path, index=False)
            artefact_paths["equity_curve"] = str(equity_path.relative_to(self._artefacts_dir))

        # Trades
        if self._all_trades:
            trades_df = pd.DataFrame([
                {
                    "trade_id": str(t.trade_id),
                    "symbol": t.symbol,
                    "bot": t.bot,
                    "side": t.side.value,
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "size": t.size,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "mae": t.mae,
                    "mfe": t.mfe,
                    "bars_held": t.bars_held,
                    "exit_reason": t.exit_reason,
                }
                for t in self._all_trades
            ])
            trades_path = run_dir / "trades.parquet"
            trades_df.to_parquet(trades_path, index=False)
            artefact_paths["trades"] = str(trades_path.relative_to(self._artefacts_dir))

        # Orders
        if self._all_orders:
            orders_df = pd.DataFrame([
                {
                    "order_id": str(o.order_id),
                    "timestamp": o.timestamp,
                    "symbol": o.symbol,
                    "bot": o.bot,
                    "action": o.action.value,
                    "size": o.size,
                    "price_requested": o.price_requested,
                    "price_filled": o.price_filled,
                    "status": o.status.value,
                    "spread_applied": o.spread_applied,
                    "slippage_applied": o.slippage_applied,
                    "fees_applied": o.fees_applied,
                    "rejection_reason": o.rejection_reason,
                }
                for o in self._all_orders
            ])
            orders_path = run_dir / "orders.parquet"
            orders_df.to_parquet(orders_path, index=False)
            artefact_paths["orders"] = str(orders_path.relative_to(self._artefacts_dir))

        # Metrics
        metrics_data = {
            "combined": combined_metrics.model_dump() if combined_metrics else {},
            "per_bot": [
                {
                    "bot": r.bot,
                    "symbols_traded": r.symbols_traded,
                    "trades_count": r.trades_count,
                    "orders_count": r.orders_count,
                    "metrics": r.metrics.model_dump(),
                }
                for r in per_bot_results
            ],
        }
        metrics_path = run_dir / "metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics_data, f, indent=2, default=str)
        artefact_paths["metrics"] = str(metrics_path.relative_to(self._artefacts_dir))

        # Warnings
        all_warnings = self._warnings + self._broker.get_warnings()
        if all_warnings:
            warnings_path = run_dir / "warnings.json"
            with open(warnings_path, "w") as f:
                json.dump({"warnings": all_warnings}, f, indent=2)
            artefact_paths["warnings"] = str(warnings_path.relative_to(self._artefacts_dir))

        logger.debug("Wrote artefacts to %s", run_dir)

        return artefact_paths

    def _emit_progress(self, data: dict[str, Any]) -> None:
        """Emit progress event."""
        if self._progress_callback:
            self._progress_callback({
                "type": "backtest_progress",
                "ts": datetime.now(UTC).isoformat(),
                **data,
            })
