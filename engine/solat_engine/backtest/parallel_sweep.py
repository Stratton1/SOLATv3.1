"""
Parallel Sweep Runner with Resume Support.

Features:
- Process-based parallelism for CPU-bound backtests
- Atomic checkpointing for resume after interruption
- LRU bar data cache to reduce I/O
- Progress reporting with ETA
- Configurable workers, timeouts, and shuffle

DOES NOT change core backtest logic - identical results to serial execution.
"""

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from multiprocessing import cpu_count
from pathlib import Path
from typing import Any

import pandas as pd

from solat_engine.backtest.models import (
    FeeConfig,
    RiskConfig,
    SlippageConfig,
    SpreadConfig,
)
from solat_engine.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SweepManifest:
    """Manifest for tracking sweep progress and enabling resume."""

    sweep_id: str
    request_hash: str
    created_at: str
    version: str = "1.0"
    total_combos: int = 0
    completed_combos: int = 0
    failed_combos: int = 0
    status: str = "running"  # running, completed, failed
    last_updated: str = ""
    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sweep_id": self.sweep_id,
            "request_hash": self.request_hash,
            "created_at": self.created_at,
            "version": self.version,
            "total_combos": self.total_combos,
            "completed_combos": self.completed_combos,
            "failed_combos": self.failed_combos,
            "status": self.status,
            "last_updated": self.last_updated,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SweepManifest":
        return cls(
            sweep_id=d["sweep_id"],
            request_hash=d["request_hash"],
            created_at=d["created_at"],
            version=d.get("version", "1.0"),
            total_combos=d.get("total_combos", 0),
            completed_combos=d.get("completed_combos", 0),
            failed_combos=d.get("failed_combos", 0),
            status=d.get("status", "running"),
            last_updated=d.get("last_updated", ""),
            config=d.get("config", {}),
        )


@dataclass
class ComboResult:
    """Result from running a single combo."""

    combo_id: str
    bot: str
    symbol: str
    timeframe: str
    success: bool
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    pnl: float = 0.0
    sortino: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pnl: float = 0.0
    error: str | None = None
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "combo_id": self.combo_id,
            "bot": self.bot,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "success": self.success,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "pnl": self.pnl,
            "sortino": self.sortino,
            "profit_factor": self.profit_factor,
            "avg_trade_pnl": self.avg_trade_pnl,
            "error": self.error,
            "duration_s": self.duration_s,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ComboResult":
        return cls(
            combo_id=d["combo_id"],
            bot=d["bot"],
            symbol=d["symbol"],
            timeframe=d["timeframe"],
            success=d["success"],
            sharpe=d.get("sharpe", 0.0),
            max_drawdown=d.get("max_drawdown", 0.0),
            win_rate=d.get("win_rate", 0.0),
            total_trades=d.get("total_trades", 0),
            pnl=d.get("pnl", 0.0),
            sortino=d.get("sortino", 0.0),
            profit_factor=d.get("profit_factor", 0.0),
            avg_trade_pnl=d.get("avg_trade_pnl", 0.0),
            error=d.get("error"),
            duration_s=d.get("duration_s", 0.0),
        )


def compute_combo_id(
    bot: str,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> str:
    """Compute deterministic hash for a combo."""
    data = f"{bot}:{symbol}:{timeframe}:{start.isoformat()}:{end.isoformat()}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def compute_request_hash(
    bots: list[str],
    symbols: list[str],
    timeframes: list[str],
    start: datetime,
    end: datetime,
    initial_cash: float,
) -> str:
    """Compute deterministic hash for sweep request configuration."""
    # Sort to ensure determinism
    data = json.dumps({
        "bots": sorted(bots),
        "symbols": sorted(symbols),
        "timeframes": sorted(timeframes),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_cash": initial_cash,
    }, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _run_single_combo(args: tuple) -> ComboResult:
    """
    Run a single backtest combo in a worker process.

    This function runs in a separate process and must not share state.
    """
    (
        combo_id,
        bot,
        symbol,
        timeframe,
        start_iso,
        end_iso,
        initial_cash,
        data_dir_str,
        spread_dict,
        slippage_dict,
        fees_dict,
        risk_dict,
    ) = args

    start_time = time.time()

    try:
        # Import inside worker to avoid pickling issues
        from datetime import datetime

        from solat_engine.backtest.engine import BacktestEngineV1
        from solat_engine.backtest.models import (
            BacktestRequest,
            FeeConfig,
            RiskConfig,
            SlippageConfig,
            SpreadConfig,
        )
        from solat_engine.data.parquet_store import ParquetStore

        data_dir = Path(data_dir_str)
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)

        # Create store (uses internal caching)
        store = ParquetStore(data_dir)

        # Create request
        request = BacktestRequest(
            symbols=[symbol],
            bots=[bot],
            timeframe=timeframe,
            start=start_dt,
            end=end_dt,
            initial_cash=initial_cash,
            spread=SpreadConfig(**spread_dict) if spread_dict else SpreadConfig(),
            slippage=SlippageConfig(**slippage_dict) if slippage_dict else SlippageConfig(),
            fees=FeeConfig(**fees_dict) if fees_dict else FeeConfig(),
            risk=RiskConfig(**risk_dict) if risk_dict else RiskConfig(),
        )

        # Run backtest
        engine = BacktestEngineV1(
            parquet_store=store,
            artefacts_dir=data_dir,
            progress_callback=None,
        )
        result = engine.run(request)

        duration = time.time() - start_time

        if result.ok and result.combined_metrics:
            m = result.combined_metrics
            return ComboResult(
                combo_id=combo_id,
                bot=bot,
                symbol=symbol,
                timeframe=timeframe,
                success=True,
                sharpe=m.sharpe_ratio or 0.0,
                max_drawdown=m.max_drawdown_pct or 0.0,
                win_rate=m.win_rate or 0.0,
                total_trades=m.total_trades,
                pnl=m.total_return or 0.0,
                sortino=m.sortino_ratio or 0.0,
                profit_factor=m.profit_factor or 0.0,
                avg_trade_pnl=m.avg_trade_pnl or 0.0,
                duration_s=duration,
            )
        else:
            return ComboResult(
                combo_id=combo_id,
                bot=bot,
                symbol=symbol,
                timeframe=timeframe,
                success=False,
                error="; ".join(result.errors[:3]) if result.errors else "No metrics",
                duration_s=duration,
            )

    except Exception as e:
        duration = time.time() - start_time
        return ComboResult(
            combo_id=combo_id,
            bot=bot,
            symbol=symbol,
            timeframe=timeframe,
            success=False,
            error=str(e)[:200],
            duration_s=duration,
        )


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".tmp_",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.rename(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


class ParallelSweepRunner:
    """
    Parallel sweep runner with resume, caching, and progress reporting.

    Usage:
        runner = ParallelSweepRunner(data_dir, max_workers=4)
        results = runner.run(
            bots=["TKCrossSniper", "KumoBreaker"],
            symbols=["EURUSD", "GBPUSD"],
            timeframes=["1h", "4h"],
            start=datetime(2023, 1, 1, tzinfo=UTC),
            end=datetime(2024, 12, 31, tzinfo=UTC),
            resume=True,
        )
    """

    def __init__(
        self,
        data_dir: Path,
        max_workers: int | None = None,
        combo_timeout: float = 300.0,
        progress_callback: Callable[[dict], None] | None = None,
    ):
        """
        Initialize parallel sweep runner.

        Args:
            data_dir: Root data directory
            max_workers: Number of parallel workers (default: cpu_count - 1)
            combo_timeout: Timeout per combo in seconds (default: 300s)
            progress_callback: Optional callback for progress events
        """
        self.data_dir = Path(data_dir)
        self.sweeps_dir = self.data_dir / "sweeps"
        self.sweeps_dir.mkdir(parents=True, exist_ok=True)

        self.max_workers = max_workers or max(1, cpu_count() - 1)
        self.combo_timeout = combo_timeout
        self.progress_callback = progress_callback

    def run(
        self,
        bots: list[str],
        symbols: list[str],
        timeframes: list[str],
        start: datetime,
        end: datetime,
        initial_cash: float = 100000.0,
        spread: SpreadConfig | None = None,
        slippage: SlippageConfig | None = None,
        fees: FeeConfig | None = None,
        risk: RiskConfig | None = None,
        resume: bool = True,
        force: bool = False,
        shuffle: bool = False,
        sweep_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run parallel sweep.

        Args:
            bots: List of bot names
            symbols: List of symbols
            timeframes: List of timeframes
            start: Start datetime
            end: End datetime
            initial_cash: Initial cash
            spread/slippage/fees/risk: Trading configs
            resume: Resume from checkpoint if available
            force: Force re-run all combos even if completed
            shuffle: Shuffle combo order (helps with load balancing)
            sweep_id: Optional sweep ID (auto-generated if not provided)

        Returns:
            Dict with results, stats, and paths
        """
        import random
        from uuid import uuid4

        started_at = datetime.now(UTC)

        # Compute request hash for resume matching
        request_hash = compute_request_hash(
            bots, symbols, timeframes, start, end, initial_cash
        )

        # Find or create sweep directory
        if sweep_id and resume:
            sweep_dir = self.sweeps_dir / sweep_id
        elif resume and not force:
            # Look for existing sweep with matching hash
            sweep_dir = self._find_resumable_sweep(request_hash)
            if sweep_dir:
                sweep_id = sweep_dir.name
                logger.info("Resuming sweep %s", sweep_id)
            else:
                sweep_id = str(uuid4())[:8]
                sweep_dir = self.sweeps_dir / sweep_id
        else:
            sweep_id = str(uuid4())[:8]
            sweep_dir = self.sweeps_dir / sweep_id

        combos_dir = sweep_dir / "combos"
        combos_dir.mkdir(parents=True, exist_ok=True)

        # Generate all combos
        all_combos = [
            (bot, symbol, tf)
            for bot in bots
            for symbol in symbols
            for tf in timeframes
        ]
        total_combos = len(all_combos)

        if shuffle:
            random.shuffle(all_combos)

        # Load or create manifest
        manifest_path = sweep_dir / "manifest.json"
        if manifest_path.exists() and resume and not force:
            with open(manifest_path) as f:
                manifest = SweepManifest.from_dict(json.load(f))
            if manifest.request_hash != request_hash:
                logger.warning(
                    "Request hash mismatch (%s != %s), starting fresh",
                    manifest.request_hash, request_hash,
                )
                manifest = self._create_manifest(
                    sweep_id, request_hash, total_combos, bots, symbols, timeframes, start, end
                )
        else:
            manifest = self._create_manifest(
                sweep_id, request_hash, total_combos, bots, symbols, timeframes, start, end
            )

        # Find completed combos
        completed_combo_ids = set()
        if resume and not force:
            for combo_file in combos_dir.glob("*.json"):
                try:
                    with open(combo_file) as f:
                        combo_data = json.load(f)
                    if combo_data.get("success") is not None:
                        completed_combo_ids.add(combo_data["combo_id"])
                except Exception:
                    pass
            logger.info("Found %d completed combos to skip", len(completed_combo_ids))

        # Build work queue
        work_items = []
        spread_dict = spread.model_dump() if spread else {}
        slippage_dict = slippage.model_dump() if slippage else {}
        fees_dict = fees.model_dump() if fees else {}
        risk_dict = risk.model_dump() if risk else {}

        for bot, symbol, tf in all_combos:
            combo_id = compute_combo_id(bot, symbol, tf, start, end)
            if combo_id in completed_combo_ids:
                continue
            work_items.append((
                combo_id,
                bot,
                symbol,
                tf,
                start.isoformat(),
                end.isoformat(),
                initial_cash,
                str(self.data_dir),
                spread_dict,
                slippage_dict,
                fees_dict,
                risk_dict,
            ))

        pending_count = len(work_items)
        skipped_count = len(completed_combo_ids)

        self._emit_progress({
            "type": "sweep_started",
            "sweep_id": sweep_id,
            "total_combos": total_combos,
            "pending": pending_count,
            "skipped": skipped_count,
            "workers": self.max_workers,
        })

        logger.info(
            "Starting parallel sweep %s: %d combos (%d pending, %d skipped), %d workers",
            sweep_id, total_combos, pending_count, skipped_count, self.max_workers,
        )

        # Run parallel
        results: list[ComboResult] = []
        completed = skipped_count
        failed = 0
        durations: list[float] = []
        last_manifest_update = time.time()

        if pending_count > 0:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_combo = {
                    executor.submit(_run_single_combo, item): item
                    for item in work_items
                }

                for future in as_completed(future_to_combo):
                    try:
                        result = future.result(timeout=self.combo_timeout)
                    except Exception as e:
                        item = future_to_combo[future]
                        result = ComboResult(
                            combo_id=item[0],
                            bot=item[1],
                            symbol=item[2],
                            timeframe=item[3],
                            success=False,
                            error=f"Timeout or error: {str(e)[:100]}",
                        )

                    # Save combo result atomically
                    combo_path = combos_dir / f"{result.combo_id}.json"
                    atomic_write_json(combo_path, result.to_dict())

                    results.append(result)
                    durations.append(result.duration_s)

                    if result.success:
                        completed += 1
                    else:
                        failed += 1

                    # Progress
                    done = completed + failed - skipped_count
                    remaining = pending_count - done

                    eta_s = None
                    if durations:
                        avg_duration = sum(durations) / len(durations)
                        # Account for parallelism
                        eta_s = (remaining * avg_duration) / self.max_workers

                    self._emit_progress({
                        "type": "sweep_progress",
                        "sweep_id": sweep_id,
                        "completed": completed,
                        "failed": failed,
                        "total": total_combos,
                        "percent": round((completed + failed) / total_combos * 100, 1),
                        "eta_s": round(eta_s, 1) if eta_s else None,
                        "last_combo": f"{result.bot}/{result.symbol}/{result.timeframe}",
                        "last_sharpe": round(result.sharpe, 3) if result.success else None,
                    })

                    # Update manifest periodically
                    if time.time() - last_manifest_update > 10:
                        manifest.completed_combos = completed
                        manifest.failed_combos = failed
                        manifest.last_updated = datetime.now(UTC).isoformat()
                        atomic_write_json(manifest_path, manifest.to_dict())
                        last_manifest_update = time.time()

        # Load all results (including previously completed)
        all_results: list[ComboResult] = []
        for combo_file in combos_dir.glob("*.json"):
            try:
                with open(combo_file) as f:
                    combo_data = json.load(f)
                all_results.append(ComboResult.from_dict(combo_data))
            except Exception as e:
                logger.warning("Failed to load combo %s: %s", combo_file, e)

        # Update final manifest
        manifest.completed_combos = sum(1 for r in all_results if r.success)
        manifest.failed_combos = sum(1 for r in all_results if not r.success)
        manifest.status = "completed"
        manifest.last_updated = datetime.now(UTC).isoformat()
        atomic_write_json(manifest_path, manifest.to_dict())

        # Write consolidated results
        self._write_results(sweep_dir, all_results)

        completed_at = datetime.now(UTC)
        duration = (completed_at - started_at).total_seconds()

        self._emit_progress({
            "type": "sweep_completed",
            "sweep_id": sweep_id,
            "completed": manifest.completed_combos,
            "failed": manifest.failed_combos,
            "total": total_combos,
            "duration_s": round(duration, 1),
        })

        logger.info(
            "Sweep %s completed: %d/%d successful in %.1fs (%.1f combos/min)",
            sweep_id,
            manifest.completed_combos,
            total_combos,
            duration,
            total_combos / (duration / 60) if duration > 0 else 0,
        )

        return {
            "sweep_id": sweep_id,
            "ok": manifest.failed_combos < total_combos,
            "total_combos": total_combos,
            "completed": manifest.completed_combos,
            "failed": manifest.failed_combos,
            "duration_s": duration,
            "sweep_dir": str(sweep_dir),
            "results_path": str(sweep_dir / "results.csv"),
        }

    def _find_resumable_sweep(self, request_hash: str) -> Path | None:
        """Find an existing sweep directory with matching request hash."""
        for sweep_dir in self.sweeps_dir.iterdir():
            if not sweep_dir.is_dir():
                continue
            manifest_path = sweep_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path) as f:
                        manifest = json.load(f)
                    if manifest.get("request_hash") == request_hash and manifest.get("status") != "completed":
                        return sweep_dir
                except Exception:
                    pass
        return None

    def _create_manifest(
        self,
        sweep_id: str,
        request_hash: str,
        total_combos: int,
        bots: list[str],
        symbols: list[str],
        timeframes: list[str],
        start: datetime,
        end: datetime,
    ) -> SweepManifest:
        """Create a new sweep manifest."""
        return SweepManifest(
            sweep_id=sweep_id,
            request_hash=request_hash,
            created_at=datetime.now(UTC).isoformat(),
            total_combos=total_combos,
            config={
                "bots": bots,
                "symbols": symbols,
                "timeframes": timeframes,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )

    def _write_results(self, sweep_dir: Path, results: list[ComboResult]) -> None:
        """Write consolidated results to CSV and JSON."""
        if not results:
            return

        # Sort by sharpe descending
        results.sort(key=lambda r: r.sharpe, reverse=True)

        # CSV
        df = pd.DataFrame([r.to_dict() for r in results])
        df.to_csv(sweep_dir / "results.csv", index=False)

        # JSON
        atomic_write_json(sweep_dir / "results.json", {
            "created_at": datetime.now(UTC).isoformat(),
            "count": len(results),
            "results": [r.to_dict() for r in results],
        })

        # Summary stats
        successful = [r for r in results if r.success]
        if successful:
            summary = {
                "total": len(results),
                "successful": len(successful),
                "failed": len(results) - len(successful),
                "top_10_sharpe": [
                    {"bot": r.bot, "symbol": r.symbol, "tf": r.timeframe, "sharpe": r.sharpe}
                    for r in successful[:10]
                ],
                "avg_sharpe": sum(r.sharpe for r in successful) / len(successful),
                "max_sharpe": max(r.sharpe for r in successful),
                "avg_trades": sum(r.total_trades for r in successful) / len(successful),
            }
            atomic_write_json(sweep_dir / "summary.json", summary)

    def _emit_progress(self, data: dict) -> None:
        """Emit progress event."""
        if self.progress_callback:
            self.progress_callback({
                "ts": datetime.now(UTC).isoformat(),
                **data,
            })


def run_parallel_sweep_cli():
    """CLI entrypoint for parallel sweep."""
    import argparse

    # Python 3.10 compatibility
    import datetime as _dt
    if not hasattr(_dt, 'UTC'):
        _dt.UTC = _dt.UTC

    parser = argparse.ArgumentParser(
        description="Run parallel Grand Sweep backtest with resume support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full sweep with 4 workers
  python -m solat_engine.backtest.parallel_sweep --scope live --max-workers 4

  # Resume interrupted sweep
  python -m solat_engine.backtest.parallel_sweep --scope live --resume

  # Force re-run all combos
  python -m solat_engine.backtest.parallel_sweep --scope live --force

  # Mini test
  python -m solat_engine.backtest.parallel_sweep --scope mini --max-workers 2
        """,
    )
    parser.add_argument(
        "--scope",
        choices=["live", "all", "mini"],
        default="live",
        help="Scope: live=10 FX pairs, all=37 instruments, mini=quick test",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["1h", "4h"],
        help="Timeframes to test",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help=f"Number of parallel workers (default: {max(1, cpu_count() - 1)})",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from checkpoint if available (default: True)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't resume, start fresh (but keep existing results)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-run all combos even if completed",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle combo order for better load balancing",
    )
    parser.add_argument(
        "--combo-timeout",
        type=float,
        default=300.0,
        help="Timeout per combo in seconds (default: 300)",
    )
    parser.add_argument(
        "--sweep-id",
        type=str,
        default=None,
        help="Specific sweep ID to resume",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2023-01-01",
        help="Start date (default: 2023-01-01)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2025-12-31",
        help="End date (default: 2025-12-31)",
    )

    args = parser.parse_args()

    # Import here to avoid circular imports
    from solat_engine.strategies.elite8 import get_available_bots

    # Define scopes
    LIVE_FX_PAIRS = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
        "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
    ]
    ALL_SYMBOLS = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
        "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "EURCAD", "EURCHF", "EURNZD",
        "GBPAUD", "GBPCAD", "GBPCHF", "GBPNZD",
        "AUDJPY", "AUDNZD", "AUDCAD", "AUDCHF",
        "NZDJPY", "NZDCAD", "NZDCHF",
        "CADJPY", "CADCHF", "CHFJPY",
        "GOLD", "SILVER",
        "SP500", "NASDAQ", "DAX", "FTSE100", "NIKKEI", "ASX200", "HSI",
    ]
    ELITE_8_BOTS = get_available_bots()

    # Select scope
    if args.scope == "mini":
        symbols = ["EURUSD", "GBPUSD"]
        bots = ["TKCrossSniper", "KumoBreaker"]
    elif args.scope == "live":
        symbols = LIVE_FX_PAIRS
        bots = ELITE_8_BOTS
    else:
        symbols = ALL_SYMBOLS
        bots = ELITE_8_BOTS

    # Parse dates
    start = datetime.fromisoformat(args.start).replace(tzinfo=_dt.UTC)
    end = datetime.fromisoformat(args.end).replace(tzinfo=_dt.UTC)

    # Setup
    script_dir = Path(__file__).parent.parent.parent
    data_dir = script_dir / "data"

    total_combos = len(bots) * len(symbols) * len(args.timeframes)
    workers = args.max_workers or max(1, cpu_count() - 1)

    print(f"\n{'='*60}")
    print(f"PARALLEL GRAND SWEEP - {datetime.now().isoformat()}")
    print(f"{'='*60}")
    print(f"Bots: {len(bots)} - {', '.join(bots)}")
    print(f"Symbols: {len(symbols)}")
    print(f"Timeframes: {args.timeframes}")
    print(f"Date range: {args.start} to {args.end}")
    print(f"Total combinations: {total_combos}")
    print(f"Workers: {workers}")
    print(f"Resume: {args.resume and not args.no_resume}")
    print(f"Force: {args.force}")
    print(f"{'='*60}\n")

    # Progress callback
    last_print_time = [0.0]

    def print_progress(event: dict) -> None:
        event_type = event.get("type")
        if event_type == "sweep_started":
            print(f"Started sweep {event['sweep_id']}: {event['total_combos']} combos ({event['pending']} pending, {event['skipped']} skipped)")
        elif event_type == "sweep_progress":
            now = time.time()
            if now - last_print_time[0] >= 1.0:  # Throttle to 1/sec
                last_print_time[0] = now
                eta = f"ETA: {event['eta_s']:.0f}s" if event.get('eta_s') else ""
                sharpe = f"Sharpe={event['last_sharpe']:.3f}" if event.get('last_sharpe') is not None else ""
                print(f"\r[{event['completed']}/{event['total']}] {event['percent']:.1f}% {event.get('last_combo', '')} {sharpe} {eta}    ", end="", flush=True)
        elif event_type == "sweep_completed":
            print(f"\n\nSweep {event['sweep_id']} completed: {event['completed']}/{event['total']} in {event['duration_s']:.1f}s")

    # Run
    runner = ParallelSweepRunner(
        data_dir=data_dir,
        max_workers=workers,
        combo_timeout=args.combo_timeout,
        progress_callback=print_progress,
    )

    result = runner.run(
        bots=bots,
        symbols=symbols,
        timeframes=args.timeframes,
        start=start,
        end=end,
        resume=args.resume and not args.no_resume,
        force=args.force,
        shuffle=args.shuffle,
        sweep_id=args.sweep_id,
    )

    # Print summary
    print(f"\n{'='*60}")
    print("SWEEP SUMMARY")
    print(f"{'='*60}")
    print(f"Sweep ID: {result['sweep_id']}")
    print(f"Total: {result['total_combos']}")
    print(f"Completed: {result['completed']}")
    print(f"Failed: {result['failed']}")
    print(f"Duration: {result['duration_s']:.1f}s ({result['total_combos'] / (result['duration_s'] / 60):.1f} combos/min)")
    print(f"Results: {result['results_path']}")

    # Load and print top performers
    results_path = Path(result['results_path'])
    if results_path.exists():
        df = pd.read_csv(results_path)
        successful = df[df['success']]
        if len(successful) > 0:
            top = successful[successful['total_trades'] >= 10].nlargest(20, 'sharpe')
            if len(top) > 0:
                print("\n🏆 TOP 20 BY SHARPE (min 10 trades):")
                print(top[['bot', 'symbol', 'timeframe', 'total_trades', 'sharpe', 'win_rate', 'max_drawdown', 'pnl']].to_string(index=False))

    print(f"\n{'='*60}\n")

    return result


if __name__ == "__main__":
    run_parallel_sweep_cli()
