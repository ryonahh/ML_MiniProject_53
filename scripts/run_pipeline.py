"""Run the full experiment and write every result to ``results/``.

Usage:
    python scripts/run_pipeline.py            # full run (5 seeds)
    python scripts/run_pipeline.py --quick    # 1 seed, fewer trees - for a live demo

The full run writes results/ and the website data (docs/assets/data.js).
The quick run writes only to results/quick/, so the official results are never overwritten.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from olympic_momentum.config import RESULTS_DIR, ExperimentConfig  # noqa: E402
from olympic_momentum.experiment import run_all  # noqa: E402
from olympic_momentum.reporting import save_results  # noqa: E402
from olympic_momentum.site_data import export_site_data  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="1 seed and 100 trees (about a minute)")
    args = parser.parse_args()

    config = ExperimentConfig()
    if args.quick:
        config = replace(config, seeds=(0,), forest=replace(config.forest, n_estimators=100))

    start = time.time()
    results = run_all(config)
    out_dir = RESULTS_DIR / "quick" if args.quick else RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = save_results(results, out_dir)
    if not args.quick:
        export_site_data(results)

    print("\nRio 2016 held-out test (mean over seeds)")
    print(results["test_summary"][["MAE_mean", "RMSE_mean", "R2_mean", "Top10_MAE_mean"]].round(3))
    head = summary["headline"]
    print(f"\n{head['proposed_model']}: MAE -{head['mae_reduction_vs_baseline_pct']}% vs Baseline, "
          f"-{head['mae_reduction_vs_historical_pct']}% vs {head['reference_model']}; "
          f"beats it in {head['backtest_wins_vs_historical']}/{head['backtest_games']} backtest Games.")
    where = "results/quick/" if args.quick else "results/ and docs/assets/data.js"
    print(f"Done in {time.time() - start:.0f}s. Outputs written to {where}.")


if __name__ == "__main__":
    main()
