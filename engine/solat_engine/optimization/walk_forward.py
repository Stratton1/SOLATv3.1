"""
Walk-Forward Optimization Engine.

Implements rolling/anchored walk-forward analysis to find robust
trading strategies that generalize to out-of-sample data.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import BacktestRequest, RiskConfig
from solat_engine.config import get_settings
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger
from solat_engine.optimization.models import (
    ComboPerformance,
    OptimizationMode,
    WalkForwardConfig,
    WalkForwardResult,
    WalkForwardWindow,
    WindowType,
)
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus

logger = get_logger(__name__)


class WalkForwardEngine:
    """
    Walk-forward optimization engine.

    Performs walk-forward analysis by:
    1. Splitting data into in-sample (training) and out-of-sample (test) periods
    2. Running backtest sweep on in-sample to find best combos
    3. Validating those combos on out-of-sample data
    4. Stepping forward and repeating
    5. Aggregating results to find consistently performing combos
    """

    def __init__(
        self,
        parquet_store: ParquetStore,
        risk_config: RiskConfig | None = None,
    ):
        self.parquet_store = parquet_store
        self.risk_config = risk_config or RiskConfig()
        self.event_bus = get_event_bus()

        # Get settings for artefacts directory
        settings = get_settings()
        self.artefacts_dir = settings.data_dir / "artefacts" / "walk_forward"
        self.artefacts_dir.mkdir(parents=True, exist_ok=True)

        # Active runs
        self._active_runs: dict[str, WalkForwardResult] = {}

    async def run(
        self, config: WalkForwardConfig, run_id: str | None = None
    ) -> WalkForwardResult:
        """
        Run walk-forward optimization.

        Args:
            config: Walk-forward configuration
            run_id: Optional pre-generated run ID (auto-generated if None)

        Returns:
            Complete walk-forward result with window-by-window analysis
        """
        if run_id is None:
            run_id = f"wf-{uuid.uuid4().hex[:8]}"

        result = WalkForwardResult(
            run_id=run_id,
            config=config,
            status="running",
            started_at=datetime.now(UTC),
        )
        self._active_runs[run_id] = result

        try:
            # Generate windows
            windows = self._generate_windows(config)
            result.total_windows = len(windows)

            if not windows:
                result.status = "failed"
                result.message = "No valid windows could be generated from date range"
                return result

            logger.info(
                "Starting walk-forward %s: %d windows, %d symbols, %d bots",
                run_id,
                len(windows),
                len(config.symbols),
                len(config.bots),
            )

            # Publish start event
            await self.event_bus.publish(
                Event(
                    type=EventType.BACKTEST_STARTED,
                    run_id=run_id,
                    data={
                        "type": "walk_forward",
                        "total_windows": len(windows),
                        "symbols": config.symbols,
                        "bots": config.bots,
                    },
                )
            )

            # Process each window
            all_oos_performances: list[ComboPerformance] = []

            for i, (is_start, is_end, oos_start, oos_end) in enumerate(windows):
                window_result = await self._process_window(
                    window_id=i,
                    config=config,
                    in_sample_start=is_start,
                    in_sample_end=is_end,
                    out_of_sample_start=oos_start,
                    out_of_sample_end=oos_end,
                )

                result.windows.append(window_result)
                result.completed_windows = i + 1
                result.progress = (i + 1) / len(windows) * 100

                # Collect OOS performances
                for oos_result in window_result.out_of_sample_results:
                    perf = ComboPerformance(
                        symbol=oos_result.get("symbol", ""),
                        bot=oos_result.get("bot", ""),
                        timeframe=oos_result.get("timeframe", ""),
                        sharpe=oos_result.get("sharpe", 0),
                        sortino=oos_result.get("sortino", 0),
                        win_rate=oos_result.get("win_rate", 0),
                        profit_factor=oos_result.get("profit_factor", 0),
                        total_return_pct=oos_result.get("total_return_pct", 0),
                        max_drawdown_pct=oos_result.get("max_drawdown_pct", 0),
                        total_trades=oos_result.get("total_trades", 0),
                        window_id=i,
                        is_in_sample=False,
                    )
                    all_oos_performances.append(perf)

                # Publish progress
                await self.event_bus.publish(
                    Event(
                        type=EventType.BACKTEST_PROGRESS,
                        run_id=run_id,
                        data={
                            "progress": result.progress,
                            "window": i + 1,
                            "total_windows": len(windows),
                            "window_oos_sharpe": window_result.oos_sharpe,
                        },
                    )
                )

            # Aggregate results
            result = self._aggregate_results(result, all_oos_performances, config)

            # Write artefacts (folds.parquet, scorecard.parquet)
            self._write_artefacts(result, all_oos_performances)

            result.status = "completed"
            result.completed_at = datetime.now(UTC)
            result.message = f"Completed {len(windows)} windows, {len(result.recommended_combos)} combos recommended"

            logger.info(
                "Walk-forward %s completed: aggregate Sharpe=%.2f, %d recommended combos",
                run_id,
                result.aggregate_sharpe or 0,
                len(result.recommended_combos),
            )

            # Publish completion
            await self.event_bus.publish(
                Event(
                    type=EventType.BACKTEST_COMPLETED,
                    run_id=run_id,
                    data={
                        "type": "walk_forward",
                        "aggregate_sharpe": result.aggregate_sharpe,
                        "recommended_count": len(result.recommended_combos),
                    },
                )
            )

            return result

        except Exception as e:
            logger.exception("Walk-forward %s failed: %s", run_id, e)
            result.status = "failed"
            result.message = str(e)
            result.completed_at = datetime.now(UTC)
            return result

    @staticmethod
    def _generate_windows(
        config: WalkForwardConfig,
    ) -> list[tuple[datetime, datetime, datetime, datetime]]:
        """
        Generate walk-forward windows.

        Returns list of (in_sample_start, in_sample_end, oos_start, oos_end) tuples.

        ROLLING: IS window slides forward by step_days each iteration.
        ANCHORED: IS always starts at anchor (start_date), IS end grows by step_days.
        """
        _MAX_ITERATIONS = 10_000
        windows: list[tuple[datetime, datetime, datetime, datetime]] = []
        current_start = config.start_date

        for _ in range(_MAX_ITERATIONS):
            # In-sample period
            if config.window_type == WindowType.ANCHORED:
                is_start = config.start_date  # Always from anchor
                is_end = current_start + timedelta(days=config.in_sample_days)
            else:
                is_start = current_start
                is_end = is_start + timedelta(days=config.in_sample_days)

            # Out-of-sample period
            oos_start = is_end
            oos_end = oos_start + timedelta(days=config.out_of_sample_days)

            # Check if OOS end exceeds overall end
            if oos_end > config.end_date:
                break

            windows.append((is_start, is_end, oos_start, oos_end))

            # Step forward — both modes advance current_start uniformly
            current_start += timedelta(days=config.step_days)
        else:
            raise RuntimeError(
                f"Walk-forward window generation exceeded {_MAX_ITERATIONS} iterations. "
                f"Check step_days ({config.step_days}) and date range."
            )

        return windows

    async def _process_window(
        self,
        window_id: int,
        config: WalkForwardConfig,
        in_sample_start: datetime,
        in_sample_end: datetime,
        out_of_sample_start: datetime,
        out_of_sample_end: datetime,
    ) -> WalkForwardWindow:
        """Process a single walk-forward window."""

        logger.debug(
            "Processing window %d: IS %s-%s, OOS %s-%s",
            window_id,
            in_sample_start.date(),
            in_sample_end.date(),
            out_of_sample_start.date(),
            out_of_sample_end.date(),
        )

        # Run in-sample backtest sweep
        is_performances = await self._run_sweep(
            symbols=config.symbols,
            bots=config.bots,
            timeframes=config.timeframes,
            start=in_sample_start,
            end=in_sample_end,
            window_id=window_id,
            is_in_sample=True,
        )

        # Rank by optimization mode and select top N
        is_performances = self._filter_and_rank(
            performances=is_performances,
            mode=config.optimization_mode,
            min_trades=config.min_trades,
            max_drawdown_pct=config.max_drawdown_pct,
            min_sharpe=config.min_sharpe,
        )

        top_is = is_performances[:config.top_n]

        # Run out-of-sample validation for top in-sample combos
        oos_performances: list[ComboPerformance] = []
        if top_is:
            # Extract unique combos from top IS results
            combos_to_test = set()
            for perf in top_is:
                combos_to_test.add((perf.symbol, perf.bot, perf.timeframe))

            # Run OOS backtests for those combos
            for symbol, bot, timeframe in combos_to_test:
                oos_perf = await asyncio.to_thread(
                    self._run_single_backtest,
                    symbol,
                    bot,
                    timeframe,
                    out_of_sample_start,
                    out_of_sample_end,
                    window_id,
                    False,
                )
                if oos_perf:
                    oos_performances.append(oos_perf)

        # Calculate OOS aggregates
        oos_sharpe = None
        oos_return = None
        oos_win_rate = None
        oos_trades = 0

        if oos_performances:
            valid_sharpes = [p.sharpe for p in oos_performances if p.sharpe is not None]
            valid_returns = [p.total_return_pct for p in oos_performances]
            valid_win_rates = [p.win_rate for p in oos_performances if p.total_trades > 0]

            if valid_sharpes:
                oos_sharpe = sum(valid_sharpes) / len(valid_sharpes)
            if valid_returns:
                oos_return = sum(valid_returns) / len(valid_returns)
            if valid_win_rates:
                oos_win_rate = sum(valid_win_rates) / len(valid_win_rates)
            oos_trades = sum(p.total_trades for p in oos_performances)

        return WalkForwardWindow(
            window_id=window_id,
            in_sample_start=in_sample_start,
            in_sample_end=in_sample_end,
            out_of_sample_start=out_of_sample_start,
            out_of_sample_end=out_of_sample_end,
            in_sample_top=[self._perf_to_dict(p) for p in top_is],
            out_of_sample_results=[self._perf_to_dict(p) for p in oos_performances],
            oos_sharpe=oos_sharpe,
            oos_return_pct=oos_return,
            oos_win_rate=oos_win_rate,
            oos_trades=oos_trades,
        )

    async def _run_sweep(
        self,
        symbols: list[str],
        bots: list[str],
        timeframes: list[str],
        start: datetime,
        end: datetime,
        window_id: int,
        is_in_sample: bool,
    ) -> list[ComboPerformance]:
        """Run backtest sweep and return performance metrics."""
        performances: list[ComboPerformance] = []

        for symbol in symbols:
            for bot in bots:
                for timeframe in timeframes:
                    # Run sync backtest in thread to avoid blocking event loop
                    perf = await asyncio.to_thread(
                        self._run_single_backtest,
                        symbol,
                        bot,
                        timeframe,
                        start,
                        end,
                        window_id,
                        is_in_sample,
                    )
                    if perf:
                        performances.append(perf)

        return performances

    def _run_single_backtest(
        self,
        symbol: str,
        bot: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        window_id: int,
        is_in_sample: bool,
    ) -> ComboPerformance | None:
        """Run a single backtest and return performance."""
        try:
            # Create backtest engine
            engine = BacktestEngineV1(
                parquet_store=self.parquet_store,
                artefacts_dir=self.artefacts_dir,
            )

            # Create request with single symbol and bot
            request = BacktestRequest(
                symbols=[symbol],
                timeframe=timeframe,
                start=start,
                end=end,
                bots=[bot],
                initial_cash=10000.0,
                risk=self.risk_config,
            )

            # Run backtest (sync method)
            result = engine.run(request)

            if not result or not result.combined_metrics:
                return None

            metrics = result.combined_metrics

            return ComboPerformance(
                symbol=symbol,
                bot=bot,
                timeframe=timeframe,
                sharpe=metrics.sharpe_ratio or 0,
                sortino=metrics.sortino_ratio or 0,
                win_rate=metrics.win_rate or 0,
                profit_factor=metrics.profit_factor or 0,
                total_return_pct=metrics.total_return_pct or 0,
                max_drawdown_pct=metrics.max_drawdown_pct or 0,
                total_trades=metrics.total_trades or 0,
                window_id=window_id,
                is_in_sample=is_in_sample,
            )

        except Exception as e:
            logger.warning("Backtest failed for %s/%s/%s: %s", symbol, bot, timeframe, e)
            return None

    def _filter_and_rank(
        self,
        performances: list[ComboPerformance],
        mode: OptimizationMode,
        min_trades: int,
        max_drawdown_pct: float,
        min_sharpe: float,
    ) -> list[ComboPerformance]:
        """Filter and rank performances by optimization mode."""

        # Filter
        filtered = [
            p for p in performances
            if p.total_trades >= min_trades
            and p.max_drawdown_pct <= max_drawdown_pct
            and p.sharpe >= min_sharpe
        ]

        # Calculate composite scores
        for p in filtered:
            p.calculate_composite()

        # Sort by selected mode
        if mode == OptimizationMode.SHARPE:
            filtered.sort(key=lambda p: p.sharpe, reverse=True)
        elif mode == OptimizationMode.SORTINO:
            filtered.sort(key=lambda p: p.sortino, reverse=True)
        elif mode == OptimizationMode.WIN_RATE:
            filtered.sort(key=lambda p: p.win_rate, reverse=True)
        elif mode == OptimizationMode.PROFIT_FACTOR:
            filtered.sort(key=lambda p: p.profit_factor, reverse=True)
        elif mode == OptimizationMode.CALMAR:
            # Calmar = annualized return / max drawdown
            for p in filtered:
                calmar = (p.total_return_pct / max(p.max_drawdown_pct, 0.01))
                p.composite_score = calmar
            filtered.sort(key=lambda p: p.composite_score, reverse=True)
        else:  # COMPOSITE
            filtered.sort(key=lambda p: p.composite_score, reverse=True)

        return filtered

    def _aggregate_results(
        self,
        result: WalkForwardResult,
        all_oos_performances: list[ComboPerformance],
        config: WalkForwardConfig,
    ) -> WalkForwardResult:
        """Aggregate OOS results to find consistently performing combos."""

        if not all_oos_performances:
            return result

        # Group by combo
        combo_performances: dict[str, list[ComboPerformance]] = {}
        for perf in all_oos_performances:
            combo_id = perf.combo_id
            if combo_id not in combo_performances:
                combo_performances[combo_id] = []
            combo_performances[combo_id].append(perf)

        # Calculate average metrics per combo
        combo_averages: list[dict[str, Any]] = []
        for combo_id, perfs in combo_performances.items():
            if len(perfs) < 2:  # Need at least 2 windows to be consistent
                continue

            avg_sharpe = sum(p.sharpe for p in perfs) / len(perfs)
            avg_win_rate = sum(p.win_rate for p in perfs) / len(perfs)
            avg_return = sum(p.total_return_pct for p in perfs) / len(perfs)
            total_trades = sum(p.total_trades for p in perfs)
            avg_drawdown = sum(p.max_drawdown_pct for p in perfs) / len(perfs)

            # Consistency score: lower std dev of sharpe = more consistent
            sharpe_values = [p.sharpe for p in perfs]
            sharpe_std = (sum((s - avg_sharpe) ** 2 for s in sharpe_values) / len(sharpe_values)) ** 0.5

            # Stability metrics
            sharpe_cv = sharpe_std / max(abs(avg_sharpe), 0.01)
            folds_profitable_pct = sum(1 for p in perfs if p.sharpe > 0) / len(perfs)

            parts = combo_id.split(":")
            combo_averages.append({
                "combo_id": combo_id,
                "symbol": parts[0] if len(parts) > 0 else "",
                "bot": parts[1] if len(parts) > 1 else "",
                "timeframe": parts[2] if len(parts) > 2 else "",
                "avg_sharpe": avg_sharpe,
                "avg_win_rate": avg_win_rate,
                "avg_return_pct": avg_return,
                "total_trades": total_trades,
                "avg_drawdown_pct": avg_drawdown,
                "sharpe_std": sharpe_std,
                "sharpe_cv": sharpe_cv,
                "folds_profitable_pct": folds_profitable_pct,
                "windows_count": len(perfs),
                "consistency_score": avg_sharpe / max(sharpe_std, 0.1),  # Higher = more consistent
            })

        # Sort by consistency score and select top N
        combo_averages.sort(key=lambda x: x["consistency_score"], reverse=True)
        result.recommended_combos = combo_averages[:config.top_n]

        # Calculate aggregate metrics
        if all_oos_performances:
            valid = [p for p in all_oos_performances if p.total_trades > 0]
            if valid:
                result.aggregate_sharpe = sum(p.sharpe for p in valid) / len(valid)
                result.aggregate_win_rate = sum(p.win_rate for p in valid) / len(valid)
                result.aggregate_return_pct = sum(p.total_return_pct for p in valid) / len(valid)
            result.aggregate_trades = sum(p.total_trades for p in all_oos_performances)

        return result

    def _write_artefacts(
        self,
        result: WalkForwardResult,
        all_oos_performances: list[ComboPerformance],
    ) -> None:
        """Write folds.parquet and scorecard.parquet artefacts."""
        import pandas as pd

        run_dir = self.artefacts_dir / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # folds.parquet — one row per window x combo with IS+OOS metrics
        fold_rows = []
        for window in result.windows:
            for item in window.in_sample_top:
                fold_rows.append({
                    "window_id": window.window_id,
                    "is_start": window.in_sample_start.isoformat(),
                    "is_end": window.in_sample_end.isoformat(),
                    "oos_start": window.out_of_sample_start.isoformat(),
                    "oos_end": window.out_of_sample_end.isoformat(),
                    "period": "IS",
                    "symbol": item.get("symbol", ""),
                    "bot": item.get("bot", ""),
                    "timeframe": item.get("timeframe", ""),
                    "sharpe": item.get("sharpe", 0),
                    "sortino": item.get("sortino", 0),
                    "win_rate": item.get("win_rate", 0),
                    "profit_factor": item.get("profit_factor", 0),
                    "total_return_pct": item.get("total_return_pct", 0),
                    "max_drawdown_pct": item.get("max_drawdown_pct", 0),
                    "total_trades": item.get("total_trades", 0),
                })
            for item in window.out_of_sample_results:
                fold_rows.append({
                    "window_id": window.window_id,
                    "is_start": window.in_sample_start.isoformat(),
                    "is_end": window.in_sample_end.isoformat(),
                    "oos_start": window.out_of_sample_start.isoformat(),
                    "oos_end": window.out_of_sample_end.isoformat(),
                    "period": "OOS",
                    "symbol": item.get("symbol", ""),
                    "bot": item.get("bot", ""),
                    "timeframe": item.get("timeframe", ""),
                    "sharpe": item.get("sharpe", 0),
                    "sortino": item.get("sortino", 0),
                    "win_rate": item.get("win_rate", 0),
                    "profit_factor": item.get("profit_factor", 0),
                    "total_return_pct": item.get("total_return_pct", 0),
                    "max_drawdown_pct": item.get("max_drawdown_pct", 0),
                    "total_trades": item.get("total_trades", 0),
                })

        if fold_rows:
            try:
                pd.DataFrame(fold_rows).to_parquet(run_dir / "folds.parquet", index=False)
            except Exception as e:
                logger.warning("Failed to write folds.parquet: %s", e)

        # scorecard.parquet — recommended combos
        if result.recommended_combos:
            try:
                pd.DataFrame(result.recommended_combos).to_parquet(
                    run_dir / "scorecard.parquet", index=False
                )
            except Exception as e:
                logger.warning("Failed to write scorecard.parquet: %s", e)

        logger.debug("Wrote artefacts to %s", run_dir)

    def _perf_to_dict(self, perf: ComboPerformance) -> dict[str, Any]:
        """Convert ComboPerformance to dict for serialization."""
        return {
            "symbol": perf.symbol,
            "bot": perf.bot,
            "timeframe": perf.timeframe,
            "sharpe": perf.sharpe,
            "sortino": perf.sortino,
            "win_rate": perf.win_rate,
            "profit_factor": perf.profit_factor,
            "total_return_pct": perf.total_return_pct,
            "max_drawdown_pct": perf.max_drawdown_pct,
            "total_trades": perf.total_trades,
            "composite_score": perf.composite_score,
        }

    def get_result(self, run_id: str) -> WalkForwardResult | None:
        """Get walk-forward result by run_id."""
        return self._active_runs.get(run_id)

    def is_active(self, run_id: str) -> bool:
        """Check if a run is still active."""
        result = self._active_runs.get(run_id)
        return result is not None and result.status == "running"
