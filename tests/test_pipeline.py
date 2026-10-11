"""Unit tests for leakage-safety and correctness of the feature pipeline.

Run with:  python -m pytest -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from olympic_momentum.config import MODEL_SPECS, ForestParams  # noqa: E402
from olympic_momentum.data import aggregate_country_year  # noqa: E402
from olympic_momentum.features import (  # noqa: E402
    PerformanceMomentum,
    add_forecast_rows,
    build_temporal_features,
)
from olympic_momentum.models import MedalForecaster, regression_metrics  # noqa: E402


@pytest.fixture
def athletes() -> pd.DataFrame:
    """Tiny synthetic athlete table: a 4-person relay gold must count once."""
    rows = []
    for athlete in range(4):
        rows.append(dict(ID=athlete, NOC="AAA", Games="2000 Summer", Year=2000, Season="Summer",
                         Sport="Athletics", Event="Relay", Medal="Gold", Country="Alpha"))
    rows.append(dict(ID=10, NOC="BBB", Games="2000 Summer", Year=2000, Season="Summer",
                     Sport="Swimming", Event="100m", Medal=np.nan, Country="Beta"))
    return pd.DataFrame(rows)


@pytest.fixture
def table() -> pd.DataFrame:
    years = [2000, 2004, 2008, 2012]
    return pd.DataFrame({
        "Country": ["A"] * 4 + ["B"] * 4,
        "Year": years * 2,
        "Athletes": [10, 20, 30, 40, 5, 5, 5, 5],
        "Sports": [2, 3, 4, 5, 1, 1, 1, 1],
        "Events": [4, 6, 8, 10, 2, 2, 2, 2],
        "Gold": [1, 2, 3, 4, 0, 0, 1, 0],
        "Total_Medals": [2, 4, 8, 16, 0, 1, 1, 0],
        "Is_Host": 0,
    })


def test_team_medals_counted_once(athletes):
    result = aggregate_country_year(athletes).set_index("Country")
    assert result.loc["Alpha", "Total_Medals"] == 1
    assert result.loc["Alpha", "Athletes"] == 4
    assert result.loc["Beta", "Total_Medals"] == 0


def test_features_use_only_past_games(table):
    features = build_temporal_features(table).set_index(["Country", "Year"])
    assert features.loc[("A", 2000), "Previous_Medals"] == 0  # no history yet
    assert features.loc[("A", 2008), "Previous_Medals"] == 4
    assert features.loc[("A", 2012), "Rolling_3_Medal_Avg"] == pytest.approx((2 + 4 + 8) / 3)
    assert features.loc[("A", 2012), "Medal_Efficiency"] == pytest.approx(8 / 30)


def test_changing_future_does_not_change_past_features(table):
    before = build_temporal_features(table)
    altered = table.copy()
    altered.loc[altered["Year"] == 2012, "Total_Medals"] = 999
    after = build_temporal_features(altered)
    cols = [c for c in before.columns if c.startswith(("Previous", "Historical", "Rolling", "Medal_"))]
    pd.testing.assert_frame_equal(before[cols], after[cols])


def test_forecast_rows_get_lagged_features(table):
    extended = build_temporal_features(add_forecast_rows(table, year=2016, from_year=2012))
    row = extended[(extended["Country"] == "A") & (extended["Year"] == 2016)].iloc[0]
    assert np.isnan(row["Total_Medals"])
    assert row["Previous_Medals"] == 16


def test_momentum_scaler_is_fitted_on_training_rows_only(table):
    features = build_temporal_features(table)
    train, test = features[features["Year"] < 2012], features[features["Year"] == 2012]
    scaler = PerformanceMomentum().fit(train)
    refit = PerformanceMomentum().fit(features)
    assert not np.allclose(scaler.mean_, refit.mean_)
    assert scaler.transform(test)["Performance_Momentum"].notna().all()


@pytest.mark.parametrize("spec", MODEL_SPECS, ids=lambda s: s.name)
def test_every_model_fits_and_predicts_non_negative(table, spec):
    features = build_temporal_features(table)
    model = MedalForecaster(spec, ForestParams(n_estimators=10, min_samples_leaf=1)).fit(
        features, features["Total_Medals"]
    )
    predictions = model.predict(features)
    assert predictions.shape == (len(features),)
    assert (predictions >= 0).all()


def test_regression_metrics_perfect_prediction():
    metrics = regression_metrics([1, 2, 3], [1, 2, 3], top_k=2)
    assert metrics["MAE"] == 0 and metrics["RMSE"] == 0 and metrics["R2"] == 1
