"""Save experiment outputs: tables, JSON summary and publication figures."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import (  # noqa: E402
    FIGURES_DIR,
    MODEL_SPECS,
    PROCESSED_DIR,
    PROPOSED_MODEL,
    REFERENCE_MODEL,
    RESULTS_DIR,
    TARGET,
)

MODEL_ORDER = [spec.name for spec in MODEL_SPECS]
INK, MUTED, GRID = "#1d2433", "#6b7280", "#e5e7eb"
GOLD, NAVY, GREY = "#c9962b", "#1f3a5f", "#b8bec9"


def _style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
        "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
        "grid.color": GRID, "grid.linewidth": 0.6, "figure.dpi": 150,
        "savefig.bbox": "tight", "savefig.facecolor": "white",
    })


def _colour(model: str) -> str:
    return GOLD if model == PROPOSED_MODEL else NAVY if model == REFERENCE_MODEL else GREY


def backtest_table(backtest: pd.DataFrame) -> pd.DataFrame:
    """Mean MAE per model (rows) and Olympic year (columns)."""
    table = backtest.pivot_table(index="model", columns="year", values="MAE", aggfunc="mean")
    table["Average"] = table.mean(axis=1)
    return table.reindex(MODEL_ORDER)


# ---------------------------------------------------------------------- figures
def plot_model_comparison(summary: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    models = summary.index.tolist()
    y = np.arange(len(models))[::-1]
    ax.barh(y, summary["MAE_mean"], xerr=summary["MAE_std"], color=[_colour(m) for m in models],
            height=0.62, error_kw={"ecolor": MUTED, "elinewidth": 1, "capsize": 2})
    for yi, value in zip(y, summary["MAE_mean"]):
        ax.text(value + 0.02, yi, f"{value:.3f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, models)
    ax.set_xlabel("Mean absolute error on Rio 2016 (medals per country, lower is better)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, summary["MAE_mean"].max() * 1.18)
    fig.savefig(path)
    plt.close(fig)


def plot_backtest(table: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    years = [c for c in table.columns if c != "Average"]
    for model in table.index:
        is_key = model in (PROPOSED_MODEL, REFERENCE_MODEL, "Baseline")
        ax.plot(years, table.loc[model, years], marker="o", ms=4,
                lw=2.4 if model == PROPOSED_MODEL else 1.4,
                color=_colour(model) if is_key else GREY, alpha=1 if is_key else 0.6,
                label=model)
    ax.set_xticks(years)
    ax.set_ylabel("MAE (medals per country)")
    ax.set_xlabel("Held-out Olympic Games (trained on all earlier Games)")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.savefig(path)
    plt.close(fig)


def plot_actual_vs_predicted(pred: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    upper = max(pred[TARGET].max(), pred[PROPOSED_MODEL].max()) * 1.05
    ax.plot([0, upper], [0, upper], color=GRID, lw=1.2, zorder=1)
    ax.scatter(pred[TARGET], pred[PROPOSED_MODEL], s=22, color=GOLD, edgecolor="white",
               lw=0.5, zorder=2)
    for _, row in pred.nlargest(8, TARGET).iterrows():
        ax.annotate(row["Country"], (row[TARGET], row[PROPOSED_MODEL]), fontsize=7.5,
                    color=INK, xytext=(4, -3), textcoords="offset points")
    ax.set_xlabel("Actual medals, Rio 2016")
    ax.set_ylabel("Predicted medals")
    fig.savefig(path)
    plt.close(fig)


def plot_importance(importance: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    data = importance.iloc[::-1]
    ax.barh(data["feature"].str.replace("_", " "), data["importance"], xerr=data["std"],
            color=NAVY, height=0.6, error_kw={"ecolor": MUTED, "elinewidth": 1})
    ax.set_xlabel("Increase in 2016 MAE when shuffled")
    ax.grid(axis="y", visible=False)
    fig.savefig(path)
    plt.close(fig)


def plot_model_families(families: pd.DataFrame, path: Path) -> None:
    """Paired bars: each model family predicting the count vs predicting momentum."""
    table = families.pivot_table(index="model", columns="target", values="MAE", sort=False)
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    y = np.arange(len(table))[::-1]
    ax.barh(y + 0.19, table["Count"], height=0.36, color=GREY, label="Predict the count")
    if "Momentum" in table:
        ax.barh(y - 0.19, table["Momentum"], height=0.36, color=GOLD, label="Predict momentum (proposed)")
    for yi, (count, mom) in zip(y, table[["Count", "Momentum"]].to_numpy()):
        ax.text(count + 0.03, yi + 0.19, f"{count:.2f}", va="center", fontsize=8, color=INK)
        if not np.isnan(mom):
            ax.text(mom + 0.03, yi - 0.19, f"{mom:.2f}", va="center", fontsize=8, color=INK)
    ax.set_yticks(y, table.index)
    ax.set_xlabel("MAE on Rio 2016 (history + World Bank features)")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.savefig(path)
    plt.close(fig)


# ------------------------------------------------------------------------- save
def save_results(results: dict, results_dir: Path = RESULTS_DIR) -> dict:
    """Write CSV tables, metrics.json and figures. Returns the JSON summary."""
    _style()
    figures = results_dir / "figures" if results_dir != RESULTS_DIR else FIGURES_DIR
    figures.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    dataset: pd.DataFrame = results["dataset"]
    dataset.to_csv(PROCESSED_DIR / "country_year_features.csv", index=False)

    summary: pd.DataFrame = results["test_summary"]
    backtest = backtest_table(results["backtest"])
    summary.round(4).to_csv(results_dir / "test_2016_metrics.csv")
    backtest.round(4).to_csv(results_dir / "rolling_origin_mae.csv")
    results["test_predictions"].round(3).to_csv(results_dir / "predictions_2016.csv", index=False)
    results["forecast"].round(3).to_csv(results_dir / "forecast_2020.csv", index=False)
    results["importance"].round(4).to_csv(results_dir / "feature_importance.csv", index=False)
    results["tuning_grid"].round(4).to_csv(results_dir / "tuning_grid.csv", index=False)

    plot_model_comparison(summary, figures / "model_comparison.png")
    plot_backtest(backtest, figures / "rolling_origin.png")
    plot_actual_vs_predicted(results["test_predictions"], figures / "actual_vs_predicted_2016.png")
    plot_importance(results["importance"], figures / "feature_importance.png")

    params = results["params"]
    proposed, reference = summary.loc[PROPOSED_MODEL], summary.loc[REFERENCE_MODEL]
    baseline = summary.loc["Baseline"]
    wins = int((backtest.loc[PROPOSED_MODEL].drop("Average")
                < backtest.loc[REFERENCE_MODEL].drop("Average")).sum())
    payload = {
        "forest_params": {"n_estimators": params.n_estimators,
                          "min_samples_leaf": params.min_samples_leaf,
                          "max_features": params.max_features},
        "split": results["config"].split.__dict__,
        "seeds": list(results["config"].seeds),
        "test_2016": summary.round(4).reset_index().to_dict(orient="records"),
        "headline": {
            "proposed_model": PROPOSED_MODEL,
            "reference_model": REFERENCE_MODEL,
            "mae_reduction_vs_baseline_pct": round(100 * (1 - proposed.MAE_mean / baseline.MAE_mean), 2),
            "mae_reduction_vs_historical_pct": round(100 * (1 - proposed.MAE_mean / reference.MAE_mean), 2),
            "rmse_reduction_vs_baseline_pct": round(100 * (1 - proposed.RMSE_mean / baseline.RMSE_mean), 2),
            "backtest_wins_vs_historical": wins,
            "backtest_games": len(backtest.columns) - 1,
        },
        "significance_2016": {k: round(v, 4) for k, v in results["significance"].items()},
        "rolling_origin_mae": backtest.round(4).reset_index().to_dict(orient="records"),
    }
    families = results["model_families"]
    families.drop(columns="params").round(4).to_csv(results_dir / "model_families_2016.csv", index=False)
    results["classifiers"].round(4).to_csv(results_dir / "classifiers.csv", index=False)
    plot_model_families(families, figures / "model_families.png")
    payload["model_families_2016"] = families.drop(columns="params").round(4).to_dict(orient="records")
    payload["classifiers"] = results["classifiers"].round(4).to_dict(orient="records")

    scores = results.get("forecast_scores")
    if scores is not None:
        scores.round(4).to_csv(results_dir / "tokyo_2020_metrics.csv")
        payload["tokyo_2020"] = scores.round(4).reset_index().to_dict(orient="records")
    (results_dir / "metrics.json").write_text(json.dumps(payload, indent=2))
    return payload
