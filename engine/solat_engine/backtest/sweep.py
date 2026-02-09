"""
Grand Sweep batch runner for backtesting.

Runs all combinations of bots × symbols × timeframes and produces
ranked results.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import (
    BacktestRequest,
    SweepComboResult,
    SweepRequest,
    SweepResult,
)
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger

logger = get_logger(__name__)


def compute_params_hash(
    bot: str,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> str:
    """Compute deterministic hash for a combo's parameters."""
    data = f"{bot}:{symbol}:{timeframe}:{start.isoformat()}:{end.isoformat()}"
    return hashlib.md5(data.encode()).hexdigest()[:12]


class GrandSweep:
    """
    Batch runner for backtest sweeps.

    Runs all combinations of bots × symbols × timeframes and produces
    a ranked results table.
    """

    def __init__(
        self,
        parquet_store: ParquetStore,
        artefacts_dir: Path,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        """
        Initialize Grand Sweep runner.

        Args:
            parquet_store: Store for reading historical bars
            artefacts_dir: Directory for output artefacts
            progress_callback: Optional callback for progress events
        """
        self._store = parquet_store
        self._artefacts_dir = artefacts_dir
        self._progress_callback = progress_callback

    def run(self, request: SweepRequest) -> SweepResult:
        """
        Run Grand Sweep with given request.

        Args:
            request: Sweep configuration

        Returns:
            SweepResult with ranked results
        """
        from uuid import uuid4

        sweep_id = str(uuid4())[:8]
        started_at = datetime.now(UTC)

        logger.info(
            "Starting Grand Sweep sweep_id=%s: %d bots × %d symbols × %d timeframes",
            sweep_id,
            len(request.bots),
            len(request.symbols),
            len(request.timeframes),
        )

        # Generate all combos
        combos = [
            (bot, symbol, timeframe)
            for bot in request.bots
            for symbol in request.symbols
            for timeframe in request.timeframes
        ]
        total_combos = len(combos)

        self._emit_progress({
            "type": "sweep_started",
            "sweep_id": sweep_id,
            "total_combos": total_combos,
            "message": f"Starting sweep with {total_combos} combinations",
        })

        # Check for existing results if not force
        results_path = self._artefacts_dir / "sweeps" / sweep_id / "results.parquet"
        existing_results: dict[str, SweepComboResult] = {}

        if not request.force and results_path.exists():
            try:
                existing_df = pd.read_parquet(results_path)
                for _, row in existing_df.iterrows():
                    key = f"{row['bot']}:{row['symbol']}:{row['timeframe']}"
                    existing_results[key] = SweepComboResult(
                        bot=row["bot"],
                        symbol=row["symbol"],
                        timeframe=row["timeframe"],
                        sharpe=row["sharpe"],
                        max_drawdown=row["max_drawdown"],
                        win_rate=row["win_rate"],
                        total_trades=row["total_trades"],
                        pnl=row["pnl"],
                        params_hash=row.get("params_hash", ""),
                    )
                logger.info("Loaded %d existing results", len(existing_results))
            except Exception as e:
                logger.warning("Failed to load existing results: %s", e)

        # Run combos
        results: list[SweepComboResult] = []
        completed = 0
        failed = 0
        warnings: list[str] = []
        errors: list[str] = []

        for i, (bot, symbol, timeframe) in enumerate(combos):
            combo_key = f"{bot}:{symbol}:{timeframe}"
            params_hash = compute_params_hash(
                bot, symbol, timeframe, request.start, request.end
            )

            # Check if already completed
            if combo_key in existing_results and not request.force:
                results.append(existing_results[combo_key])
                completed += 1
                continue

            self._emit_progress({
                "type": "sweep_progress",
                "sweep_id": sweep_id,
                "bot": bot,
                "symbol": symbol,
                "timeframe": timeframe,
                "done": i,
                "total": total_combos,
                "message": f"Running {bot}/{symbol}/{timeframe}",
            })

            # Create backtest request for this combo
            bt_request = BacktestRequest(
                symbols=[symbol],
                timeframe=timeframe,
                start=request.start,
                end=request.end,
                bots=[bot],
                initial_cash=request.initial_cash,
                spread=request.spread,
                slippage=request.slippage,
                fees=request.fees,
                risk=request.risk,
            )

            # Run backtest
            try:
                engine = BacktestEngineV1(
                    parquet_store=self._store,
                    artefacts_dir=self._artefacts_dir,
                    progress_callback=None,  # Don't forward individual progress
                )

                bt_result = engine.run(bt_request)

                if bt_result.ok and bt_result.combined_metrics:
                    metrics = bt_result.combined_metrics
                    combo_result = SweepComboResult(
                        bot=bot,
                        symbol=symbol,
                        timeframe=timeframe,
                        sharpe=metrics.sharpe_ratio,
                        max_drawdown=metrics.max_drawdown_pct,
                        win_rate=metrics.win_rate,
                        total_trades=metrics.total_trades,
                        pnl=metrics.total_return,
                        params_hash=params_hash,
                    )
                    results.append(combo_result)
                    completed += 1

                    warnings.extend(bt_result.warnings)
                else:
                    failed += 1
                    errors.extend(bt_result.errors)

            except Exception as e:
                logger.exception("Failed to run combo %s: %s", combo_key, e)
                failed += 1
                errors.append(f"Combo {combo_key} failed: {str(e)}")

        # Sort by Sharpe ratio (descending)
        results.sort(key=lambda r: r.sharpe, reverse=True)

        # Top performers (top 10)
        top_performers = results[:10] if results else []

        # Write results
        artefact_path = self._write_results(sweep_id, results, request)

        self._emit_progress({
            "type": "sweep_completed",
            "sweep_id": sweep_id,
            "completed": completed,
            "failed": failed,
            "message": f"Sweep completed: {completed}/{total_combos} successful",
        })

        completed_at = datetime.now(UTC)

        logger.info(
            "Grand Sweep completed sweep_id=%s: %d/%d successful, top Sharpe=%.2f",
            sweep_id,
            completed,
            total_combos,
            top_performers[0].sharpe if top_performers else 0.0,
        )

        return SweepResult(
            sweep_id=sweep_id,
            ok=failed < total_combos,  # OK if at least one succeeded
            started_at=started_at,
            completed_at=completed_at,
            total_combos=total_combos,
            completed_combos=completed,
            failed_combos=failed,
            results=results,
            top_performers=top_performers,
            artefact_path=artefact_path,
            warnings=warnings[:100],  # Limit warnings
            errors=errors[:100],
        )

    def _write_results(
        self,
        sweep_id: str,
        results: list[SweepComboResult],
        request: SweepRequest,
    ) -> str | None:
        """Write sweep results to disk."""
        if not results:
            return None

        sweep_dir = self._artefacts_dir / "sweeps" / sweep_id
        sweep_dir.mkdir(parents=True, exist_ok=True)

        # Results parquet
        results_df = pd.DataFrame([
            {
                "bot": r.bot,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "sharpe": r.sharpe,
                "max_drawdown": r.max_drawdown,
                "win_rate": r.win_rate,
                "total_trades": r.total_trades,
                "pnl": r.pnl,
                "params_hash": r.params_hash,
            }
            for r in results
        ])
        results_path = sweep_dir / "results.parquet"
        results_df.to_parquet(results_path, index=False)

        # Also write JSON for easy inspection
        results_json_path = sweep_dir / "results.json"
        with open(results_json_path, "w") as f:
            json.dump(
                {
                    "sweep_id": sweep_id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "request": {
                        "bots": request.bots,
                        "symbols": request.symbols,
                        "timeframes": request.timeframes,
                        "start": request.start.isoformat(),
                        "end": request.end.isoformat(),
                    },
                    "results": [r.model_dump() for r in results],
                },
                f,
                indent=2,
                default=str,
            )

        logger.debug("Wrote sweep results to %s", sweep_dir)

        return str(results_path.relative_to(self._artefacts_dir))

    def _emit_progress(self, data: dict[str, Any]) -> None:
        """Emit progress event."""
        if self._progress_callback:
            self._progress_callback({
                "ts": datetime.now(UTC).isoformat(),
                **data,
            })
