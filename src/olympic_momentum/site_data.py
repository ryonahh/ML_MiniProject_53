"""Export experiment results as a compact JS data file for the project website."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import MODEL_SPECS, PROPOSED_MODEL, REFERENCE_MODEL, SITE_DATA_PATH, TARGET
from .reporting import backtest_table

HISTORY_START = 1964


def _round(values, digits: int = 2) -> list:
    return [None if pd.isna(v) else round(float(v), digits) for v in values]


def _country_histories(df: pd.DataFrame, countries: list[str]) -> dict:
    observed = df.dropna(subset=[TARGET])
    observed = observed[observed["Year"] >= HISTORY_START]
    out = {}
    for country, group in observed[observed["Country"].isin(countries)].groupby("Country"):
        group = group.sort_values("Year")
        out[country] = {
            "years": group["Year"].astype(int).tolist(),
            "medals": group[TARGET].astype(int).tolist(),
            "gold": group["Gold"].astype(int).tolist(),
            "athletes": group["Athletes"].astype(int).tolist(),
        }
    return out


def build_site_payload(results: dict) -> dict:
    df: pd.DataFrame = results["dataset"]
    pred: pd.DataFrame = results["test_predictions"]
    future: pd.DataFrame = results["forecast"]
    summary: pd.DataFrame = results["test_summary"]

    scores: pd.DataFrame | None = results.get("forecast_scores")
    if "Actual" not in future:
        future = future.assign(Actual=np.nan)

    # Countries worth showing: any medal in the test or forecast window.
    medal_countries = sorted(
        set(pred.loc[pred[TARGET] > 0, "Country"])
        | set(future.loc[(future["Predicted_Medals"] >= 0.5) | (future["Actual"] > 0), "Country"])
    )
    pred = pred[pred["Country"].isin(medal_countries) | (pred[PROPOSED_MODEL] >= 0.5)]

    model_names = [spec.name for spec in MODEL_SPECS]
    backtest = backtest_table(results["backtest"])
    years = [int(c) for c in backtest.columns if c != "Average"]

    return {
        "meta": {
            "proposed": PROPOSED_MODEL,
            "reference": REFERENCE_MODEL,
            "params": {k: getattr(results["params"], k)
                       for k in ("n_estimators", "min_samples_leaf", "max_features")},
            "seeds": len(results["config"].seeds),
            "countries": int(df.loc[df["Year"] == 2016, "Country"].nunique()),
            "rows": int(df[TARGET].notna().sum()),
            "forecast_countries": int(len(future)),
        },
        "tokyo": None if scores is None else [
            {"name": name, **{k: round(float(v), 4) for k, v in row.items()}}
            for name, row in scores.iterrows()
        ],
        "models": [
            {"name": spec.name, "description": spec.description, "target": spec.target,
             **{k: round(float(summary.loc[spec.name, k]), 4)
                for k in ("MAE_mean", "MAE_std", "RMSE_mean", "R2_mean", "Top10_MAE_mean")}}
            for spec in MODEL_SPECS
        ],
        "significance": {k: round(float(v), 4) for k, v in results["significance"].items()},
        "backtest": {"years": years,
                     "series": {m: _round(backtest.loc[m, years], 4) for m in model_names},
                     "average": {m: round(float(backtest.loc[m, "Average"]), 4) for m in model_names}},
        "importance": [
            {"feature": r.feature, "value": round(float(r.importance), 4), "std": round(float(r.std), 4)}
            for r in results["importance"].itertuples()
        ],
        "predictions2016": [
            {"country": r["Country"], "actual": int(r[TARGET]), "previous": int(r["Previous_Medals"]),
             **{m: round(float(r[m]), 2) for m in model_names}}
            for _, r in pred.sort_values(TARGET, ascending=False).iterrows()
        ],
        "forecast2020": [
            {"country": r["Country"], "predicted": round(float(r["Predicted_Medals"]), 2),
             "historical": round(float(r[REFERENCE_MODEL]), 2),
             "previous": int(r["Previous_Medals"]), "change": round(float(r["Predicted_Change"]), 4),
             "momentum": round(float(r["Momentum_Score"]), 3),
             "actual": None if pd.isna(r["Actual"]) else int(r["Actual"])}
            for _, r in future[future["Country"].isin(medal_countries)].iterrows()
        ],
        "history": _country_histories(df, medal_countries),
        "families": [
            {"model": r.model, "target": r.target, "MAE": round(float(r.MAE), 4),
             "RMSE": round(float(r.RMSE), 4), "Top10": round(float(r.Top10_MAE), 4)}
            for r in results["model_families"].itertuples()
        ],
        "classifiers": [
            {"model": r.model, "acc2012": round(float(r.accuracy_2012), 4), "acc2016": round(float(r.accuracy_2016), 4),
             "f12016": round(float(r.f1_2016), 4)}
            for r in results["classifiers"].itertuples()
        ],
        "economicCoverage": round(float(df.loc[df["Year"].between(1964, 2016) & df[TARGET].notna(), "Log_GDP"].notna().mean()), 3),
    }


def export_site_data(results: dict, path: Path = SITE_DATA_PATH) -> Path:
    """Write ``window.OLYMPIC_DATA = {...}`` so the static site works from file:// too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(build_site_payload(results), separators=(",", ":"))
    path.write_text(f"window.OLYMPIC_DATA = {payload};\n")
    return path
