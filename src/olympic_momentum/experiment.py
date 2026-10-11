"""Experiments: tuning, held-out test, rolling-origin backtest, significance, forecast."""

from __future__ import annotations

from dataclasses import replace
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from .config import (
    FOREST_GRID,
    MODEL_SPECS,
    PROPOSED_MODEL,
    REFERENCE_MODEL,
    TARGET,
    TOKYO_ACTUALS_CSV,
    ExperimentConfig,
    ForestParams,
    ModelSpec,
    TemporalSplit,
)
from .data import build_country_year_table
from .economic import add_economic_features
from .features import PerformanceMomentum, add_forecast_rows, build_temporal_features
from .model_zoo import run_model_zoo
from .models import fit_forecaster, regression_metrics


# --------------------------------------------------------------------------- data
def prepare_dataset(split: TemporalSplit) -> pd.DataFrame:
    """Country x Year table with temporal and World Bank features, plus empty forecast rows."""
    table = build_country_year_table()
    table = add_forecast_rows(table, year=split.forecast_year, from_year=split.test_year)
    return add_economic_features(build_temporal_features(table))


def games(df: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    """Rows for the Games held between ``start`` and ``end`` (inclusive)."""
    return df.loc[df["Year"].between(start, end)]


# ------------------------------------------------------------------------- tuning
def tune_forest(df: pd.DataFrame, config: ExperimentConfig) -> tuple[ForestParams, pd.DataFrame]:
    """Pick one shared forest setting by mean validation MAE across all models.

    Trains on ``train_start..train_end`` and scores on the validation Games
    only; the test Games are never touched here.
    """
    split = config.split
    train = games(df, split.train_start, split.train_end)
    valid = games(df, split.validation_year, split.validation_year)

    rows = []
    for leaf, max_features in product(FOREST_GRID["min_samples_leaf"], FOREST_GRID["max_features"]):
        params = replace(config.forest, min_samples_leaf=leaf, max_features=max_features)
        for spec in MODEL_SPECS:
            model = fit_forecaster(spec, params, train)
            mae = regression_metrics(valid[TARGET], model.predict(valid))["MAE"]
            rows.append({"min_samples_leaf": leaf, "max_features": max_features,
                         "model": spec.name, "validation_MAE": mae})

    grid = pd.DataFrame(rows)
    summary = grid.groupby(["min_samples_leaf", "max_features"])["validation_MAE"].mean()
    best_leaf, best_features = summary.idxmin()
    best = replace(config.forest, min_samples_leaf=int(best_leaf), max_features=float(best_features))
    return best, grid


# -------------------------------------------------------------------- evaluation
def evaluate_on_year(
    df: pd.DataFrame, year: int, train_start: int, params: ForestParams, seeds: tuple[int, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on every Games before ``year`` and score each model on ``year``.

    Returns per-seed metrics and the seed-averaged predictions for every country.
    """
    train = games(df, train_start, year - 1)
    test = games(df, year, year)

    metric_rows, predictions = [], {}
    for spec in MODEL_SPECS:
        seed_preds = []
        for seed in seeds:
            model = fit_forecaster(spec, replace(params, random_state=seed), train)
            pred = model.predict(test)
            seed_preds.append(pred)
            metric_rows.append({"year": year, "model": spec.name, "seed": seed,
                                **regression_metrics(test[TARGET], pred)})
        predictions[spec.name] = np.mean(seed_preds, axis=0)

    pred_frame = test[["Country", "Year", TARGET, "Previous_Medals"]].reset_index(drop=True)
    for name, values in predictions.items():
        pred_frame[name] = values
    return pd.DataFrame(metric_rows), pred_frame


def summarise(metrics: pd.DataFrame) -> pd.DataFrame:
    """Mean and standard deviation of every metric across seeds, per model."""
    order = [spec.name for spec in MODEL_SPECS]
    numeric = metrics.drop(columns=["seed", "year"], errors="ignore")
    summary = numeric.groupby("model").agg(["mean", "std"])
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    return summary.reindex(order)


def rolling_origin(df: pd.DataFrame, config: ExperimentConfig, params: ForestParams) -> pd.DataFrame:
    """Expanding-window backtest: for each Games, train on all earlier Games."""
    frames = [
        evaluate_on_year(df, year, config.split.train_start, params, config.seeds)[0]
        for year in config.rolling_origin_years
    ]
    return pd.concat(frames, ignore_index=True)


def bootstrap_mae_difference(
    y_true, pred_a, pred_b, n_samples: int, seed: int = 0
) -> dict[str, float]:
    """Paired bootstrap of MAE(a) - MAE(b) over countries.

    Negative values mean model *a* has lower error. Returns the observed
    difference, a 95% confidence interval and the share of resamples where
    *a* beats *b*.
    """
    rng = np.random.default_rng(seed)
    err_a = np.abs(np.asarray(y_true) - np.asarray(pred_a))
    err_b = np.abs(np.asarray(y_true) - np.asarray(pred_b))
    diff = err_a - err_b
    idx = rng.integers(0, len(diff), size=(n_samples, len(diff)))
    boot = diff[idx].mean(axis=1)
    return {
        "observed": float(diff.mean()),
        "ci_low": float(np.percentile(boot, 2.5)),
        "ci_high": float(np.percentile(boot, 97.5)),
        "prob_a_better": float((boot < 0).mean()),
    }


def feature_importance(
    df: pd.DataFrame, spec: ModelSpec, params: ForestParams, split: TemporalSplit
) -> pd.DataFrame:
    """Permutation importance (increase in test MAE when a feature is shuffled)."""
    train = games(df, split.train_start, split.test_year - 1)
    test = games(df, split.test_year, split.test_year)
    model = fit_forecaster(spec, params, train)
    X = test[list(spec.features)]
    result = permutation_importance(
        model, X, test[TARGET], scoring="neg_mean_absolute_error",
        n_repeats=20, random_state=params.random_state, n_jobs=1,
    )
    return (
        pd.DataFrame({"feature": X.columns, "importance": result.importances_mean,
                      "std": result.importances_std})
        .sort_values("importance", ascending=False, ignore_index=True)
    )


def forecast(df: pd.DataFrame, params: ForestParams, split: TemporalSplit,
             seeds: tuple[int, ...]) -> pd.DataFrame:
    """Train every model on all Games up to the test year and forecast the next Games.

    The dataset ends in 2016, so this is a genuine forecast: nothing about the
    forecast Games is available to any model.
    """
    train = games(df, split.train_start, split.test_year)
    future = games(df, split.forecast_year, split.forecast_year)
    out = future[["Country", "Year", "Previous_Medals", "Previous_Gold"]].reset_index(drop=True)

    for spec in MODEL_SPECS:
        preds, changes = [], []
        for seed in seeds:
            model = fit_forecaster(spec, replace(params, random_state=seed), train)
            preds.append(model.predict(future))
            if spec.name == PROPOSED_MODEL:
                changes.append(model.predicted_momentum(future))
        out[spec.name] = np.mean(preds, axis=0)
        if changes:
            out["Predicted_Change"] = np.mean(changes, axis=0)

    out["Predicted_Medals"] = out[PROPOSED_MODEL]
    out["Momentum_Score"] = PerformanceMomentum().fit(train).score(future).to_numpy()
    return out.sort_values("Predicted_Medals", ascending=False, ignore_index=True)


def load_actuals(path: Path = TOKYO_ACTUALS_CSV) -> pd.Series | None:
    """Actual medal totals for the forecast Games, if the file is present."""
    if not path.exists():
        return None
    return pd.read_csv(path, comment="#").set_index("Country")["Total"]


def score_forecast(future: pd.DataFrame, actuals: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach actual results to the forecast and score every model.

    Countries that competed but are absent from the medal table won 0 medals.
    """
    future = future.assign(Actual=future["Country"].map(actuals).fillna(0).astype(int))
    rows = [{"model": spec.name, **regression_metrics(future["Actual"], future[spec.name])}
            for spec in MODEL_SPECS]
    return future, pd.DataFrame(rows).set_index("model")


# ----------------------------------------------------------------------- driver
def run_all(config: ExperimentConfig | None = None, verbose: bool = True) -> dict:
    """Run every experiment and return all results in one dictionary."""
    config = config or ExperimentConfig()
    split = config.split
    log = print if verbose else (lambda *a, **k: None)
    specs = {spec.name: spec for spec in MODEL_SPECS}

    log("1/7  Building Country x Year dataset ...")
    df = prepare_dataset(split)

    log("2/7  Tuning shared Random Forest settings on the validation Games ...")
    params, tuning_grid = tune_forest(df, config)
    log(f"     -> min_samples_leaf={params.min_samples_leaf}, max_features={params.max_features}")

    log(f"3/7  Held-out test on {split.test_year} (train {split.train_start}-{split.validation_year}) ...")
    test_metrics, test_predictions = evaluate_on_year(
        df, split.test_year, split.train_start, params, config.seeds
    )
    test_summary = summarise(test_metrics)
    significance = bootstrap_mae_difference(
        test_predictions[TARGET], test_predictions[PROPOSED_MODEL],
        test_predictions[REFERENCE_MODEL], config.bootstrap_samples,
    )

    log("4/7  Rolling-origin backtest ...")
    backtest = rolling_origin(df, config, params)

    log("5/7  Permutation feature importance ...")
    importance = feature_importance(df, specs[PROPOSED_MODEL], params, split)

    log(f"6/7  Forecasting {split.forecast_year} ...")
    future = forecast(df, params, split, config.seeds)
    forecast_scores = None
    actuals = load_actuals()
    if actuals is not None:
        future, forecast_scores = score_forecast(future, actuals)

    log("7/7  Comparing the reference paper's model families ...")
    zoo = run_model_zoo(df, config, params)

    return {
        "model_families": zoo["regressors"],
        "classifiers": zoo["classifiers"],
        "forecast_scores": forecast_scores,
        "config": config,
        "params": params,
        "dataset": df,
        "tuning_grid": tuning_grid,
        "test_metrics": test_metrics,
        "test_summary": test_summary,
        "test_predictions": test_predictions,
        "significance": significance,
        "backtest": backtest,
        "importance": importance,
        "forecast": future,
    }
