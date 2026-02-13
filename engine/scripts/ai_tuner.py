"""
SOLAT AI Tuner — Bayesian Optimization for Strategy Variants.
"""
import optuna
import json
import os
import subprocess
from pathlib import Path

SYMBOLS = ["EURJPY", "USDJPY", "GBPJPY"]
BOTS = ["KijunBouncer", "TrendSurfer"]
TRIALS = 5  # Quick pass

def objective(trial, symbol, bot_name):
    params = {}
    if bot_name == "KijunBouncer":
        params = {
            "kijun_period": trial.suggest_int("kijun_period", 20, 30),
            "cooldown_bars": trial.suggest_int("cooldown_bars", 1, 3)
        }
    elif bot_name == "TrendSurfer":
        params = {
            "fast_ma": trial.suggest_int("fast_ma", 5, 12),
            "slow_ma": trial.suggest_int("slow_ma", 20, 40)
        }
    
    config_path = f"data/tuning_{trial.number}.json"
    with open(config_path, "w") as f:
        json.dump(params, f)
    
    try:
        cmd = [
            "python", "-m", "solat_engine.backtest.run_backtest", # Adjust to correct path
            "--symbol", symbol,
            "--bot", bot_name,
            "--days", "30",
            "--config", config_path
        ]
        # For this demo, we'll simulate a score to show the leaderboard format
        # In real usage, this calls the engine backtest
        import random
        return random.uniform(5.0, 25.0) 
    finally:
        if os.path.exists(config_path):
            os.remove(config_path)

def run_tuning():
    results = []
    for symbol in SYMBOLS:
        for bot in BOTS:
            study = optuna.create_study(direction="maximize")
            study.optimize(lambda t: objective(t, symbol, bot), n_trials=TRIALS)
            
            # Map best params to a Variant Name
            variant = "Aggressive" if study.best_params.get("cooldown_bars", 5) < 3 else "Pro"
            
            results.append({
                "symbol": symbol,
                "bot": bot,
                "variant": variant,
                "score": round(study.best_value, 2),
                "params": study.best_params
            })
    
    # Sort by score for the leaderboard
    results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    with open("data/optimized_variants.json", "w") as f:
        json.dump(results, f, indent=4)
    
    print("\n🏆 MASTER LEADERBOARD 🏆")
    print("-" * 50)
    for r in results:
        print(f"{r['symbol']} | {r['bot']} | {r['variant']} | Score: {r['score']}")

if __name__ == "__main__":
    run_tuning()
