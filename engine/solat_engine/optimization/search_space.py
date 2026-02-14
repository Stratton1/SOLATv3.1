"""
Per-bot Optuna search space definitions and param conversion utilities.

Each bot has a frozen dataclass for params. This module defines:
1. Optuna trial -> dict suggestion functions per bot
2. dict -> frozen dataclass conversion (dict_to_params)
3. frozen dataclass -> dict conversion (params_to_dict)
4. Default params as dict (get_default_params_dict)
"""

from typing import Any

from solat_engine.strategies.elite8_hardened import (
    BaseHardeningParams,
    ChikouConfirmerParams,
    ChikouKaizenParams,
    CloudTwistParams,
    KijunBouncerParams,
    KumoBreakerParams,
    MomentumRiderParams,
    ReversalHunterParams,
    TKCrossSniperParams,
    TrendSurferParams,
)

# ============================================================================
# Search Space Functions (Optuna Trial -> dict)
# ============================================================================


def _tk_cross_sniper_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 3, 12),
        "breakout_atr_mult": trial.suggest_float("breakout_atr_mult", 0.2, 1.0),
        "cloud_clear_atr_mult": trial.suggest_float("cloud_clear_atr_mult", 0.1, 0.8),
    }


def _kumo_breaker_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 3, 12),
        "breakout_atr_mult": trial.suggest_float("breakout_atr_mult", 0.2, 1.0),
        "breakout_retest_enabled": trial.suggest_categorical("breakout_retest_enabled", [True, False]),
        "retest_tolerance_atr_mult": trial.suggest_float("retest_tolerance_atr_mult", 0.05, 0.5),
    }


def _chikou_confirmer_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 2, 10),
    }


def _kijun_bouncer_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 4, 16),
        "impulse_atr_mult": trial.suggest_float("impulse_atr_mult", 1.0, 4.0),
        "kijun_touch_tolerance": trial.suggest_float("kijun_touch_tolerance", 0.0003, 0.003),
    }


def _cloud_twist_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 4, 16),
        "breakout_atr_mult": trial.suggest_float("breakout_atr_mult", 0.1, 0.8),
    }


def _momentum_rider_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 3, 12),
    }


def _trend_surfer_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 3, 12),
        "pullback_entry_enabled": trial.suggest_categorical("pullback_entry_enabled", [True, False]),
    }


def _reversal_hunter_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 5, 20),
        "explosive_atr_pct_block": trial.suggest_float("explosive_atr_pct_block", 0.003, 0.012),
    }


def _chikou_kaizen_space(trial: Any) -> dict[str, Any]:
    return {
        "cooldown_bars": trial.suggest_int("cooldown_bars", 3, 12),
        "displacement": trial.suggest_int("displacement", 20, 35),
        "sl_atr_mult": trial.suggest_float("sl_atr_mult", 0.5, 2.5),
        "tp_atr_mult": trial.suggest_float("tp_atr_mult", 1.0, 4.0),
    }


BOT_SEARCH_SPACES: dict[str, Any] = {
    "TKCrossSniper": _tk_cross_sniper_space,
    "KumoBreaker": _kumo_breaker_space,
    "ChikouConfirmer": _chikou_confirmer_space,
    "KijunBouncer": _kijun_bouncer_space,
    "CloudTwist": _cloud_twist_space,
    "MomentumRider": _momentum_rider_space,
    "TrendSurfer": _trend_surfer_space,
    "ReversalHunter": _reversal_hunter_space,
    "ChikouKaizen": _chikou_kaizen_space,
}


# ============================================================================
# Bot name -> Params dataclass mapping
# ============================================================================

_BOT_PARAMS_CLASS: dict[str, type] = {
    "TKCrossSniper": TKCrossSniperParams,
    "KumoBreaker": KumoBreakerParams,
    "ChikouConfirmer": ChikouConfirmerParams,
    "KijunBouncer": KijunBouncerParams,
    "CloudTwist": CloudTwistParams,
    "MomentumRider": MomentumRiderParams,
    "TrendSurfer": TrendSurferParams,
    "ReversalHunter": ReversalHunterParams,
    "ChikouKaizen": ChikouKaizenParams,
}


def dict_to_params(bot_name: str, param_dict: dict[str, Any]) -> Any:
    """
    Convert a flat param dict to the bot's frozen dataclass.

    The dict keys map to: cooldown_bars, breakout_atr_mult -> BaseHardeningParams,
    and bot-specific keys go to the outer dataclass.
    """
    if bot_name not in _BOT_PARAMS_CLASS:
        raise ValueError(f"Unknown bot: {bot_name}. Available: {list(_BOT_PARAMS_CLASS.keys())}")

    # Split into base params and bot-specific params
    base_keys = {"cooldown_bars", "breakout_atr_mult"}
    base_dict: dict[str, Any] = {}
    specific_dict: dict[str, Any] = {}

    for k, v in param_dict.items():
        if k in base_keys:
            base_dict[k] = v
        else:
            specific_dict[k] = v

    # Build base params with overrides
    defaults = get_default_params_dict(bot_name)
    default_base = {k: defaults[k] for k in base_keys if k in defaults}
    default_base.update(base_dict)
    base = BaseHardeningParams(**default_base)

    # Build outer params
    cls = _BOT_PARAMS_CLASS[bot_name]
    return cls(base=base, **specific_dict)


def params_to_dict(bot_name: str, params: Any) -> dict[str, Any]:
    """
    Convert a frozen params dataclass to a flat dict.
    """
    if params is None:
        return get_default_params_dict(bot_name)

    result: dict[str, Any] = {}

    # Extract base params
    if hasattr(params, "base"):
        base = params.base
        result["cooldown_bars"] = base.cooldown_bars
        result["breakout_atr_mult"] = base.breakout_atr_mult

    # Extract bot-specific params
    for field_name in _get_specific_fields(bot_name):
        if hasattr(params, field_name):
            result[field_name] = getattr(params, field_name)

    return result


def get_default_params_dict(bot_name: str) -> dict[str, Any]:
    """Return default params as a flat dict for a given bot."""
    if bot_name not in _BOT_PARAMS_CLASS:
        raise ValueError(f"Unknown bot: {bot_name}")

    cls = _BOT_PARAMS_CLASS[bot_name]
    default_instance = cls()
    return params_to_dict(bot_name, default_instance)


def _get_specific_fields(bot_name: str) -> list[str]:
    """Get bot-specific (non-base) field names."""
    field_map: dict[str, list[str]] = {
        "TKCrossSniper": ["cloud_clear_atr_mult"],
        "KumoBreaker": ["breakout_retest_enabled", "retest_tolerance_atr_mult"],
        "ChikouConfirmer": [],
        "KijunBouncer": ["impulse_atr_mult", "kijun_touch_tolerance"],
        "CloudTwist": [],
        "MomentumRider": [],
        "TrendSurfer": ["pullback_entry_enabled"],
        "ReversalHunter": ["explosive_atr_pct_block"],
        "ChikouKaizen": ["displacement", "sl_atr_mult", "tp_atr_mult"],
    }
    return field_map.get(bot_name, [])


def get_available_bots() -> list[str]:
    """Return list of bot names with search spaces."""
    return list(BOT_SEARCH_SPACES.keys())
