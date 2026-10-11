"""Medal forecasting models and evaluation metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin, clone
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from .config import MOMENTUM_SCORE, TARGET, ForestParams, ModelSpec
from .features import PerformanceMomentum


class ColumnSelector(BaseEstimator, TransformerMixin):
    """Keep only the requested columns, in a fixed order."""

    def __init__(self, columns: tuple[str, ...]):
        self.columns = columns

    def fit(self, X: pd.DataFrame, y=None) -> "ColumnSelector":
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return X[list(self.columns)]


class TwoStageRegressor(BaseEstimator, RegressorMixin):
    """Hurdle model from the reference paper.

    A classifier first decides whether a country wins any medal; a regressor
    trained only on medal-winning rows then estimates how many.
    """

    def __init__(self, params: ForestParams | None = None):
        self.params = params

    def fit(self, X: pd.DataFrame, y) -> "TwoStageRegressor":
        params = (self.params or ForestParams()).as_dict()
        y = np.asarray(y, dtype=float)
        won = y > 0
        clf_params = {k: v for k, v in params.items() if k != "max_features"}
        self.classifier_ = RandomForestClassifier(**clf_params).fit(X, won)
        self.regressor_ = RandomForestRegressor(**params).fit(X[won], y[won])
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        wins = self.classifier_.predict(X).astype(bool)
        return np.where(wins, self.regressor_.predict(X), 0.0)


class MedalForecaster(BaseEstimator, RegressorMixin):
    """Feature pipeline + learner + target formulation for one :class:`ModelSpec`.

    Inputs are the full feature frame (``X`` must contain ``Previous_Medals``).
    ``estimator`` optionally replaces the Random Forest with any regressor
    (it should include its own preprocessing, e.g. imputation and scaling).

    * ``target="level"``    -> the learner predicts ``Total_Medals`` directly.
    * ``target="momentum"`` -> the learner predicts
      ``log1p(medals_t) - log1p(medals_{t-1})``, the country's momentum, and
      the forecast is ``expm1(log1p(medals_{t-1}) + predicted_change)``.

    Tree ensembles cannot extrapolate beyond the targets they have seen, so
    learning *change* instead of *level* lets one tree leaf serve both a
    3-medal and a 90-medal nation with the same trajectory.
    """

    def __init__(self, spec: ModelSpec, params: ForestParams | None = None, estimator=None):
        self.spec = spec
        self.params = params
        self.estimator = estimator

    def _build_pipeline(self) -> Pipeline:
        params = self.params or ForestParams()
        steps: list[tuple[str, object]] = []
        if MOMENTUM_SCORE in self.spec.features:
            steps.append(("momentum", PerformanceMomentum()))
        steps.append(("select", ColumnSelector(self.spec.features)))
        if self.estimator is not None:
            # Any scikit-learn regressor (used by the model-family comparison).
            steps.append(("model", clone(self.estimator)))
        elif self.spec.learner == "two_stage":
            steps.append(("model", TwoStageRegressor(params)))
        else:
            steps.append(("model", RandomForestRegressor(**params.as_dict())))
        return Pipeline(steps)

    def _encode(self, X: pd.DataFrame, y) -> np.ndarray:
        y = np.asarray(y, dtype=float)
        if self.spec.target == "momentum":
            return np.log1p(y) - np.log1p(X["Previous_Medals"].to_numpy(dtype=float))
        return y

    def _decode(self, X: pd.DataFrame, raw: np.ndarray) -> np.ndarray:
        if self.spec.target == "momentum":
            raw = np.expm1(np.log1p(X["Previous_Medals"].to_numpy(dtype=float)) + raw)
        return np.clip(raw, 0.0, None)

    def fit(self, X: pd.DataFrame, y) -> "MedalForecaster":
        self.pipeline_ = self._build_pipeline().fit(X, self._encode(X, y))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self._decode(X, self.pipeline_.predict(X))

    def predicted_momentum(self, X: pd.DataFrame) -> np.ndarray:
        """Predicted log-change in medals (only meaningful for momentum targets)."""
        return self.pipeline_.predict(X)


def make_forecaster(spec: ModelSpec, params: ForestParams) -> MedalForecaster:
    return clone(MedalForecaster(spec, params))


def fit_forecaster(spec: ModelSpec, params: ForestParams, train: pd.DataFrame) -> MedalForecaster:
    return make_forecaster(spec, params).fit(train, train[TARGET])


def regression_metrics(y_true, y_pred, top_k: int = 10) -> dict[str, float]:
    """MAE, RMSE and R^2, plus MAE on the top-k medal-winning countries.

    The top-k score mirrors the second objective of the reference paper:
    errors on the leading nations matter most to anyone reading a medal table.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    top = np.argsort(-y_true)[:top_k]
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
        f"Top{top_k}_MAE": float(mean_absolute_error(y_true[top], y_pred[top])),
    }
