"""Export the Momentum Target forest to docs/assets/model.js for the website's live predictor.

Usage:
    python scripts/export_predictor.py

The full pipeline (scripts/run_pipeline.py) also runs this step.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import json  # noqa: E402

from olympic_momentum.config import RESULTS_DIR, ExperimentConfig, ForestParams  # noqa: E402
from olympic_momentum.experiment import prepare_dataset  # noqa: E402
from olympic_momentum.export_model import export_predictor  # noqa: E402


def main() -> None:
    config = ExperimentConfig()
    tuned = json.loads((RESULTS_DIR / "metrics.json").read_text())["forest_params"]
    params = ForestParams(min_samples_leaf=tuned["min_samples_leaf"], max_features=tuned["max_features"])
    path = export_predictor(prepare_dataset(config.split), params, config.split)
    print(f"Wrote {path} ({path.stat().st_size // 1024} KB); exported trees match scikit-learn.")


if __name__ == "__main__":
    main()
