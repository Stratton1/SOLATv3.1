"""
Optuna 2-stage parameter tuner.

Stage 1: TPE trials (fast single-period backtests) -> proxy score
Stage 2: Top-N params -> walk-forward validation -> tunedA (best score) + tunedB (best DD)
"""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import BacktestRequest, RiskConfig
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger
from solat_engine.optimization.scoring import ComboScore, score_combo
from solat_engine.optimization.search_space import (
    BOT_SEARCH_SPACES,
    dict_to_params,
    get_default_params_dict,
    params_to_dict,
)

logger = get_logger(__name__)


@dataclass
class TuningConfig:
    """Configuration for parameter tuning."""

    bot: str
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    n_trials: int = 40
    seed: int = 42
    initial_cash: float = 100_000.0
    top_n_for_wf: int = 5
    data_dir: Path = field(default_factory=lambda: Path("data"))
    wf_folds: int = 5
    wf_in_sample_pct: float = 0.70


@dataclass
class VariantResult:
    """Result for a single tuned variant."""

    variant_id: str
    params: dict[str, Any]
    params_diff: dict[str, Any]
    score_total: float
    oos_sharpe: float
    oos_return_pct: float
    max_drawdown_pct: float
    total_trades: int = 0
    win_rate: float = 0.0
    folds_profitable_pct: float = 0.0
    wf_run_id: str | None = None


@dataclass
class TuningResult:
    """Complete tuning result for a single combo."""

    bot: str
    symbol: str
    timeframe: str
    baseline_score: float
    tuned_a: VariantResult | None = None
    tuned_b: VariantResult | None = None
    stage1_trials: int = 0
    stage1_top_n: list[dict[str, Any]] = field(default_factory=list)
    duration_s: float = 0.0


class ParamTuner:
    """Two-stage parameter tuner using Optuna TPE + walk-forward validation."""

    def __init__(
        self,
        parquet_store: ParquetStore,
        artefacts_dir: Path,
    ):
        self._store = parquet_store
        self._artefacts_dir = artefacts_dir
        self._artefacts_dir.mkdir(parents=True, exist_ok=True)

    def tune_combo(self, config: TuningConfig) -> TuningResult:
        """
        Run 2-stage tuning for a single bot/symbol/timeframe combo.

        Stage 1: n_trials TPE optimizations using single-period backtest
        Stage 2: Top-N params validated via walk-forward folds
        """
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        t0 = time.time()

        if config.bot not in BOT_SEARCH_SPACES:
            raise ValueError(f"No search space defined for bot: {config.bot}")

        # --- Baseline score ---
        baseline_score = self._run_single_backtest_score(
            config, get_default_params_dict(config.bot)
        )

        # --- Stage 1: TPE Optimization ---
        space_fn = BOT_SEARCH_SPACES[config.bot]

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=config.seed),
        )

        def objective(trial: optuna.Trial) -> float:
            params_dict = space_fn(trial)
            return self._stage1_objective(config, params_dict)

        study.optimize(objective, n_trials=config.n_trials)

        # Collect top-N unique param sets
        trials_sorted = sorted(study.trials, key=lambda t: t.value or 0, reverse=True)
        seen_params: list[dict[str, Any]] = []
        top_n_params: list[dict[str, Any]] = []

        for trial in trials_sorted:
            if trial.value is None:
                continue
            p = dict(trial.params)
            # Deduplicate
            if p not in seen_params:
                seen_params.append(p)
                top_n_params.append(p)
            if len(top_n_params) >= config.top_n_for_wf:
                break

        # --- Stage 2: Walk-Forward Validation ---
        tuned_a, tuned_b = self._stage2_validate(config, top_n_params)

        duration = time.time() - t0

        return TuningResult(
            bot=config.bot,
            symbol=config.symbol,
            timeframe=config.timeframe,
            baseline_score=baseline_score,
            tuned_a=tuned_a,
            tuned_b=tuned_b,
            stage1_trials=len(study.trials),
            stage1_top_n=[
                {"params": p, "stage1_score": trials_sorted[i].value}
                for i, p in enumerate(top_n_params)
            ],
            duration_s=round(duration, 1),
        )

    def _stage1_objective(self, config: TuningConfig, params_dict: dict[str, Any]) -> float:
        """Single backtest with trial params -> proxy score."""
        return self._run_single_backtest_score(config, params_dict)

    def _run_single_backtest_score(
        self,
        config: TuningConfig,
        params_dict: dict[str, Any],
    ) -> float:
        """Run a single backtest and return its proxy score (0-100)."""
        engine = BacktestEngineV1(
            parquet_store=self._store,
            artefacts_dir=self._artefacts_dir,
        )

        request = BacktestRequest(
            symbols=[config.symbol],
            bots=[config.bot],
            timeframe=config.timeframe,
            start=config.start,
            end=config.end,
            initial_cash=config.initial_cash,
            params_override={config.bot: params_dict},
        )

        result = engine.run(request)

        if not result.ok or not result.combined_metrics:
            return 0.0

        m = result.combined_metrics
        # Use scoring system as proxy (with relaxed gates for tuning)
        cs = score_combo({
            "bot": config.bot,
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "oos_sharpe": m.sharpe_ratio,
            "oos_return_pct": m.total_return_pct,
            "max_drawdown_pct": m.max_drawdown_pct * 100 if m.max_drawdown_pct < 1 else m.max_drawdown_pct,
            "total_trades": m.total_trades,
            "trades_per_day": m.trades_per_day,
            "folds_profitable_pct": 1.0,  # Single period, assume 100%
            "sharpe_cv": 0.0,
            "exposure_time_pct": m.time_in_market_pct * 100,
        })

        return cs.score_total

    def _stage2_validate(
        self,
        config: TuningConfig,
        top_params: list[dict[str, Any]],
    ) -> tuple[VariantResult | None, VariantResult | None]:
        """
        Walk-forward validation on top-N param sets.

        Returns (tunedA=best score, tunedB=best drawdown).
        """
        if not top_params:
            return None, None

        # Generate WF folds
        total_days = (config.end - config.start).days
        fold_days = total_days // config.wf_folds
        if fold_days < 14:
            # Not enough data for WF, use single period
            return self._single_period_validate(config, top_params)

        in_sample_days = int(fold_days * config.wf_in_sample_pct)
        oos_days = fold_days - in_sample_days

        validated: list[dict[str, Any]] = []

        for params_dict in top_params:
            fold_scores: list[float] = []
            fold_sharpes: list[float] = []
            fold_dds: list[float] = []
            fold_returns: list[float] = []
            total_trades = 0
            total_win = 0
            total_count = 0

            for fold_idx in range(config.wf_folds):
                fold_start = config.start + timedelta(days=fold_idx * fold_days)
                oos_start = fold_start + timedelta(days=in_sample_days)
                oos_end = oos_start + timedelta(days=oos_days)

                if oos_end > config.end:
                    break

                # Run OOS backtest
                engine = BacktestEngineV1(
                    parquet_store=self._store,
                    artefacts_dir=self._artefacts_dir,
                )
                request = BacktestRequest(
                    symbols=[config.symbol],
                    bots=[config.bot],
                    timeframe=config.timeframe,
                    start=oos_start,
                    end=oos_end,
                    initial_cash=config.initial_cash,
                    params_override={config.bot: params_dict},
                )
                result = engine.run(request)

                if result.ok and result.combined_metrics:
                    m = result.combined_metrics
                    fold_sharpes.append(m.sharpe_ratio)
                    dd_val = m.max_drawdown_pct * 100 if m.max_drawdown_pct < 1 else m.max_drawdown_pct
                    fold_dds.append(dd_val)
                    fold_returns.append(m.total_return_pct)
                    total_trades += m.total_trades
                    total_win += m.winning_trades
                    total_count += m.total_trades
                    fold_scores.append(1.0 if m.sharpe_ratio > 0 else 0.0)

            if not fold_sharpes:
                continue

            # Aggregate fold metrics
            avg_sharpe = sum(fold_sharpes) / len(fold_sharpes)
            avg_dd = sum(fold_dds) / len(fold_dds) if fold_dds else 0.0
            avg_return = sum(fold_returns) / len(fold_returns) if fold_returns else 0.0
            folds_profitable = sum(fold_scores) / len(fold_scores) if fold_scores else 0.0

            # CV of sharpe
            if len(fold_sharpes) > 1 and avg_sharpe != 0:
                import statistics
                sharpe_cv = statistics.stdev(fold_sharpes) / abs(avg_sharpe)
            else:
                sharpe_cv = 0.0

            win_rate = total_win / total_count if total_count > 0 else 0.0

            # Score the aggregated metrics
            cs = score_combo({
                "bot": config.bot,
                "symbol": config.symbol,
                "timeframe": config.timeframe,
                "oos_sharpe": avg_sharpe,
                "oos_return_pct": avg_return,
                "max_drawdown_pct": avg_dd,
                "total_trades": total_trades,
                "trades_per_day": total_trades / max((config.end - config.start).days, 1),
                "folds_profitable_pct": folds_profitable,
                "sharpe_cv": sharpe_cv,
                "exposure_time_pct": 50.0,
                "oos_trades": total_trades,
                "win_rate": win_rate,
            })

            # Compute diff vs default
            default_params = get_default_params_dict(config.bot)
            diff = {k: v for k, v in params_dict.items() if default_params.get(k) != v}

            validated.append({
                "params": params_dict,
                "params_diff": diff,
                "score_total": cs.score_total,
                "oos_sharpe": avg_sharpe,
                "oos_return_pct": avg_return,
                "max_drawdown_pct": avg_dd,
                "total_trades": total_trades,
                "win_rate": win_rate,
                "folds_profitable_pct": folds_profitable,
            })

        if not validated:
            return None, None

        # tunedA = highest score
        validated.sort(key=lambda v: v["score_total"], reverse=True)
        best = validated[0]
        tuned_a = VariantResult(
            variant_id="tunedA",
            params=best["params"],
            params_diff=best["params_diff"],
            score_total=best["score_total"],
            oos_sharpe=best["oos_sharpe"],
            oos_return_pct=best["oos_return_pct"],
            max_drawdown_pct=best["max_drawdown_pct"],
            total_trades=best["total_trades"],
            win_rate=best["win_rate"],
            folds_profitable_pct=best["folds_profitable_pct"],
        )

        # tunedB = lowest max_drawdown among top scorers (score > 0)
        dd_candidates = [v for v in validated if v["score_total"] > 0]
        tuned_b = None
        if dd_candidates:
            dd_candidates.sort(key=lambda v: v["max_drawdown_pct"])
            dd_best = dd_candidates[0]
            # Only create tunedB if it's different from tunedA
            if dd_best["params"] != best["params"]:
                tuned_b = VariantResult(
                    variant_id="tunedB",
                    params=dd_best["params"],
                    params_diff=dd_best["params_diff"],
                    score_total=dd_best["score_total"],
                    oos_sharpe=dd_best["oos_sharpe"],
                    oos_return_pct=dd_best["oos_return_pct"],
                    max_drawdown_pct=dd_best["max_drawdown_pct"],
                    total_trades=dd_best["total_trades"],
                    win_rate=dd_best["win_rate"],
                    folds_profitable_pct=dd_best["folds_profitable_pct"],
                )

        return tuned_a, tuned_b

    def _single_period_validate(
        self,
        config: TuningConfig,
        top_params: list[dict[str, Any]],
    ) -> tuple[VariantResult | None, VariantResult | None]:
        """Fallback: validate with a single train/test split."""
        split_point = config.start + (config.end - config.start) * 0.7
        validated: list[dict[str, Any]] = []

        for params_dict in top_params:
            engine = BacktestEngineV1(
                parquet_store=self._store,
                artefacts_dir=self._artefacts_dir,
            )
            request = BacktestRequest(
                symbols=[config.symbol],
                bots=[config.bot],
                timeframe=config.timeframe,
                start=split_point,
                end=config.end,
                initial_cash=config.initial_cash,
                params_override={config.bot: params_dict},
            )
            result = engine.run(request)

            if result.ok and result.combined_metrics:
                m = result.combined_metrics
                default_params = get_default_params_dict(config.bot)
                diff = {k: v for k, v in params_dict.items() if default_params.get(k) != v}
                dd_val = m.max_drawdown_pct * 100 if m.max_drawdown_pct < 1 else m.max_drawdown_pct
                score = self._run_single_backtest_score(config, params_dict)
                validated.append({
                    "params": params_dict,
                    "params_diff": diff,
                    "score_total": score,
                    "oos_sharpe": m.sharpe_ratio,
                    "oos_return_pct": m.total_return_pct,
                    "max_drawdown_pct": dd_val,
                    "total_trades": m.total_trades,
                    "win_rate": m.win_rate,
                    "folds_profitable_pct": 1.0,
                })

        if not validated:
            return None, None

        validated.sort(key=lambda v: v["score_total"], reverse=True)
        best = validated[0]
        tuned_a = VariantResult(
            variant_id="tunedA",
            params=best["params"],
            params_diff=best["params_diff"],
            score_total=best["score_total"],
            oos_sharpe=best["oos_sharpe"],
            oos_return_pct=best["oos_return_pct"],
            max_drawdown_pct=best["max_drawdown_pct"],
            total_trades=best["total_trades"],
            win_rate=best["win_rate"],
            folds_profitable_pct=best.get("folds_profitable_pct", 1.0),
        )

        tuned_b = None
        dd_cands = [v for v in validated if v["score_total"] > 0 and v["params"] != best["params"]]
        if dd_cands:
            dd_cands.sort(key=lambda v: v["max_drawdown_pct"])
            dd_best = dd_cands[0]
            tuned_b = VariantResult(
                variant_id="tunedB",
                params=dd_best["params"],
                params_diff=dd_best["params_diff"],
                score_total=dd_best["score_total"],
                oos_sharpe=dd_best["oos_sharpe"],
                oos_return_pct=dd_best["oos_return_pct"],
                max_drawdown_pct=dd_best["max_drawdown_pct"],
                total_trades=dd_best["total_trades"],
                win_rate=dd_best["win_rate"],
                folds_profitable_pct=dd_best.get("folds_profitable_pct", 1.0),
            )

        return tuned_a, tuned_b
