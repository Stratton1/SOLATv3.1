"""
SOLAT Portfolio Builder CLI.

Usage:
    # Build portfolio from scored combos
    python3 scripts/build_portfolio.py --scored data/tuning/{run_id}/scored_combos.json

    # Build and write allowlist
    python3 scripts/build_portfolio.py --scored data/tuning/{run_id}/scored_combos.json --apply-allowlist
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from solat_engine.optimization.portfolio_builder import (
    PortfolioBuilder,
    PortfolioConstraints,
)
from solat_engine.optimization.scoring import ComboScore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOLAT Portfolio Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--scored", type=str, required=True, help="Path to scored_combos.json")
    parser.add_argument("--max-slots", type=int, default=25, help="Max portfolio slots")
    parser.add_argument("--min-score", type=float, default=40.0, help="Min score to include")
    parser.add_argument("--max-per-symbol", type=int, default=2, help="Max slots per symbol")
    parser.add_argument("--max-per-bot", type=int, default=6, help="Max slots per bot family")
    parser.add_argument("--max-per-currency", type=int, default=8, help="Max slots per currency")
    parser.add_argument("--risk-per-trade", type=float, default=1.0, help="Risk per trade %%")
    parser.add_argument("--apply-allowlist", action="store_true", help="Write allowlist.json")
    parser.add_argument("--data-dir", type=str, default="data", help="Data directory")
    args = parser.parse_args()

    scored_path = Path(args.scored)
    if not scored_path.exists():
        print(f"ERROR: Scored combos file not found: {scored_path}")
        sys.exit(1)

    with open(scored_path) as f:
        scored_data = json.load(f)

    # Convert to ComboScore objects
    combos: list[ComboScore] = []
    for entry in scored_data:
        combos.append(ComboScore(
            bot=entry.get("bot", ""),
            symbol=entry.get("symbol", ""),
            timeframe=entry.get("timeframe", ""),
            variant_id=entry.get("variant_id", "baseline"),
            params_override=entry.get("params_override", {}),
            score_total=entry.get("score_total", 0.0),
            oos_sharpe=entry.get("oos_sharpe", 0.0),
            oos_return_pct=entry.get("oos_return_pct", 0.0),
            max_drawdown_pct=entry.get("max_drawdown_pct", 0.0),
            total_trades=entry.get("total_trades", 0),
            win_rate=entry.get("win_rate", 0.0),
        ))

    constraints = PortfolioConstraints(
        max_slots=args.max_slots,
        min_score=args.min_score,
        max_per_symbol=args.max_per_symbol,
        max_per_bot_family=args.max_per_bot,
        max_per_currency=args.max_per_currency,
        risk_per_trade_pct=args.risk_per_trade,
    )

    print(f"\n{'='*60}")
    print("SOLAT PORTFOLIO BUILDER")
    print(f"{'='*60}")
    print(f"Input combos: {len(combos)}")
    print(f"Constraints: max_slots={constraints.max_slots}, min_score={constraints.min_score}")
    print(f"{'='*60}\n")

    builder = PortfolioBuilder()
    result = builder.build(combos, constraints)

    # Print report
    report = builder.to_markdown_report(result)
    print(report)

    # Write outputs
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        data_dir = Path(__file__).parent.parent / "data"

    run_id = f"portfolio_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    out_dir = data_dir / "portfolio" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Portfolio JSON
    portfolio_path = out_dir / "portfolio.json"
    with open(portfolio_path, "w") as f:
        json.dump({
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "total_slots": result.total_slots,
            "avg_score": result.avg_score,
            "constraints": {
                "max_slots": constraints.max_slots,
                "min_score": constraints.min_score,
                "max_per_symbol": constraints.max_per_symbol,
                "max_per_bot_family": constraints.max_per_bot_family,
                "max_per_currency": constraints.max_per_currency,
                "risk_per_trade_pct": constraints.risk_per_trade_pct,
            },
            "slots": [
                {
                    "rank": s.rank,
                    "bot": s.bot,
                    "symbol": s.symbol,
                    "timeframe": s.timeframe,
                    "variant_id": s.variant_id,
                    "params_override": s.params_override,
                    "score_total": s.score_total,
                    "risk_per_trade_pct": s.risk_per_trade_pct,
                    "oos_sharpe": s.oos_sharpe,
                    "max_drawdown_pct": s.max_drawdown_pct,
                    "win_rate": s.win_rate,
                    "total_trades": s.total_trades,
                }
                for s in result.slots
            ],
            "distributions": {
                "symbol": result.symbol_distribution,
                "bot": result.bot_distribution,
                "timeframe": result.timeframe_distribution,
                "currency": result.currency_distribution,
            },
        }, f, indent=2, default=str)

    # Markdown report
    report_path = out_dir / "PORTFOLIO_REPORT.md"
    with open(report_path, "w") as f:
        f.write(report)

    print(f"\nPortfolio JSON: {portfolio_path}")
    print(f"Report: {report_path}")

    # Allowlist
    if args.apply_allowlist:
        allowlist = builder.to_allowlist(result)
        allowlist_path = out_dir / "allowlist.json"
        with open(allowlist_path, "w") as f:
            json.dump(
                [entry.model_dump(mode="json") for entry in allowlist],
                f, indent=2, default=str,
            )
        print(f"Allowlist: {allowlist_path}")

        # Also write to standard location
        std_path = data_dir / "allowlist.json"
        with open(std_path, "w") as f:
            json.dump(
                [entry.model_dump(mode="json") for entry in allowlist],
                f, indent=2, default=str,
            )
        print(f"Standard allowlist updated: {std_path}")

    print(f"\n{'='*60}")
    print(f"PORTFOLIO BUILD COMPLETE: {result.total_slots} slots, avg score {result.avg_score:.1f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
