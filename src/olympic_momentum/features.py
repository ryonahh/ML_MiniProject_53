"""Leakage-free temporal features and the Performance Momentum transformer.

Every feature for a country at Games *t* is computed from that country's
earlier appearances only (``shift`` within the country), so nothing from the
target Games, or any later Games, can reach the model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from .config import MOMENTUM_COMPONENTS


def build_temporal_features(table: pd.DataFrame) -> pd.DataFrame:
    """Add lagged participation, trend and efficiency features to a Country x Year table."""
    df = table.sort_values(["Country", "Year"]).reset_index(drop=True).copy()
    by_country = df.groupby("Country", sort=False)

    def lag(column: str, periods: int = 1) -> pd.Series:
        return by_country[column].shift(periods)

    df["Previous_Medals"] = lag("Total_Medals")
    df["Previous_Gold"] = lag("Gold")
    df["Previous_Athletes"] = lag("Athletes")
    df["Previous_Sports"] = lag("Sports")
    df["Previous_Events"] = lag("Events")

    # Growth between the last two appearances, on a log scale so that going
    # from 1 to 3 medals and from 30 to 90 medals read as the same trend.
    df["Historical_Medal_Growth"] = np.log1p(df["Previous_Medals"]) - np.log1p(lag("Total_Medals", 2))
    df["Historical_Athlete_Growth"] = np.log1p(df["Previous_Athletes"]) - np.log1p(lag("Athletes", 2))

    df["Rolling_3_Medal_Avg"] = by_country["Total_Medals"].transform(
        lambda s: s.shift(1).rolling(window=3, min_periods=1).mean()
    )
    df["Medal_Efficiency"] = df["Previous_Medals"] / df["Previous_Athletes"].replace(0, np.nan)
    df["Appearances"] = by_country.cumcount()

    feature_columns = [
        "Previous_Medals", "Previous_Gold", "Previous_Athletes", "Previous_Sports",
        "Previous_Events", "Historical_Medal_Growth", "Historical_Athlete_Growth",
        "Rolling_3_Medal_Avg", "Medal_Efficiency",
    ]
    # A country with no (or one) previous appearance has no trend yet: zero is
    # the neutral value for every one of these features.
    df[feature_columns] = df[feature_columns].fillna(0.0)
    return df


def add_forecast_rows(table: pd.DataFrame, year: int, from_year: int) -> pd.DataFrame:
    """Append empty rows for ``year`` for every country that competed in ``from_year``.

    The outcome columns stay NaN; the lagged features are then filled in by
    :func:`build_temporal_features`, which lets us forecast Games that are not
    in the dataset (e.g. Tokyo 2020 from data up to Rio 2016).
    """
    countries = table.loc[table["Year"] == from_year, "Country"].unique()
    future = pd.DataFrame({"Country": countries, "Year": year})
    return pd.concat([table, future], ignore_index=True)


class PerformanceMomentum(BaseEstimator, TransformerMixin):
    """Append a composite *Performance Momentum* score to the feature matrix.

    Momentum = mean of the z-scored components (medal growth, athlete growth,
    medal efficiency). The means and standard deviations are learned in
    ``fit`` - i.e. from the training Games only - and re-used unchanged for
    validation, test and forecast rows, so standardisation cannot leak
    information from the future.
    """

    def __init__(self, components: list[str] | None = None, output: str = "Performance_Momentum"):
        self.components = components
        self.output = output

    def _components(self) -> list[str]:
        return list(self.components or MOMENTUM_COMPONENTS)

    def fit(self, X: pd.DataFrame, y=None) -> "PerformanceMomentum":
        values = X[self._components()]
        self.mean_ = values.mean()
        self.std_ = values.std(ddof=0).replace(0, 1.0)
        return self

    def score(self, X: pd.DataFrame) -> pd.Series:  # noqa: D401 - not an sklearn score
        z = (X[self._components()] - self.mean_) / self.std_
        return z.mean(axis=1).rename(self.output)

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        out = X.copy()
        out[self.output] = self.score(X)
        return out

    def get_feature_names_out(self, input_features=None):
        return np.asarray(list(input_features or []) + [self.output], dtype=object)
