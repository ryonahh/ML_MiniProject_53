"""Export the Momentum Target forest to JavaScript for the website's live predictor.

The forest is trained on every Games from 1964 to 2016, exactly like the 2020
forecast, and written as compact arrays (feature, threshold, children, value)
that a few lines of JavaScript can walk. ``verify_export`` checks that the
exported trees reproduce scikit-learn's predictions.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .config import HISTORICAL_FEATURES, MODEL_SPECS, PROJECT_ROOT, PROPOSED_MODEL, TARGET, ForestParams, TemporalSplit
from .models import fit_forecaster

PREDICTOR_PATH = PROJECT_ROOT / "docs" / "assets" / "model.js"
EXPORT_TREES = 100  # fewer trees than the 300 used in experiments keeps the file small


def _country_inputs(df: pd.DataFrame, split: TemporalSplit) -> dict:
    """Raw inputs per country for the forecast Games: the slider starting values."""
    observed = df.dropna(subset=[TARGET]).sort_values("Year")
    future = df[df["Year"] == split.forecast_year]
    out = {}
    for country in future["Country"]:
        hist = observed[observed["Country"] == country].tail(3)
        if hist.empty:
            continue
        medals = hist[TARGET].astype(int).tolist()[::-1]  # most recent first
        athletes = hist["Athletes"].astype(int).tolist()[::-1]
        last = hist.iloc[-1]
        out[country] = {
            "m": medals + [None] * (3 - len(medals)),
            "a": athletes[:2] + [None] * (2 - len(athletes[:2])),
            "g": int(last["Gold"]), "s": int(last["Sports"]), "e": int(last["Events"]),
        }
    return out


def _tree_arrays(tree) -> dict:
    t = tree.tree_
    leaf = t.children_left == -1
    return {
        "f": np.where(leaf, -1, t.feature).tolist(),
        # Full precision: scikit-learn compares float32 inputs against these thresholds.
        "t": [float(v) for v in np.where(leaf, 0, t.threshold)],
        "l": t.children_left.tolist(),
        "r": t.children_right.tolist(),
        "v": [round(float(v), 6) for v in t.value[:, 0, 0]],
    }


def train_predictor(df: pd.DataFrame, params: ForestParams, split: TemporalSplit):
    spec = next(s for s in MODEL_SPECS if s.name == PROPOSED_MODEL)
    train = df[df["Year"].between(split.train_start, split.test_year)]
    return fit_forecaster(spec, replace(params, n_estimators=EXPORT_TREES), train)


def export_predictor(df: pd.DataFrame, params: ForestParams, split: TemporalSplit,
                     path: Path = PREDICTOR_PATH) -> Path:
    model = train_predictor(df, params, split)
    forest = model.pipeline_.named_steps["model"]
    payload = {
        "features": list(model.spec.features),
        "trees": [_tree_arrays(est) for est in forest.estimators_],
        "countries": _country_inputs(df, split),
        "trainedOn": f"{split.train_start}-{split.test_year}",
    }
    assert payload["features"] == HISTORICAL_FEATURES
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"window.MEDAL_MODEL = {json.dumps(payload, separators=(',', ':'))};\n")
    verify_export(model, payload, df[df["Year"] == split.forecast_year])
    return path


def predict_from_export(payload: dict, X: np.ndarray) -> np.ndarray:
    """Same tree walk the website does, used to verify the export.

    Inputs are rounded to float32 first, as scikit-learn does (the website uses Math.fround).
    """
    X = np.asarray(X, dtype=np.float32).astype(float)
    out = np.zeros(len(X))
    for tree in payload["trees"]:
        for i, row in enumerate(X):
            node = 0
            while tree["f"][node] != -1:
                node = tree["l"][node] if row[tree["f"][node]] <= tree["t"][node] else tree["r"][node]
            out[i] += tree["v"][node]
    return out / len(payload["trees"])


def verify_export(model, payload: dict, rows: pd.DataFrame) -> None:
    X = rows[payload["features"]].to_numpy(dtype=float)
    exported = predict_from_export(payload, X)
    expected = model.predicted_momentum(rows)
    if not np.allclose(exported, expected, atol=1e-4):
        raise AssertionError("Exported forest does not reproduce scikit-learn predictions")
