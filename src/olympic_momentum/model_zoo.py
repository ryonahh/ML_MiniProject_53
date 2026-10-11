"""The reference paper's model families, re-run on our data, splits and features.

Regressors (Linear, Ridge, Lasso, Poisson, SVR, Random Forest) are each tried
with both targets, the medal count and the proposed momentum target, so we can
see whether predicting momentum helps beyond Random Forests. Classifiers
(Logistic Regression, SVM, Gaussian Naive Bayes, MLP, Random Forest) reproduce
the paper's medal / no-medal stage.

Every model is tuned on the 2012 validation Games (trained on 1964-2008), then
refitted on 1964-2012 and scored once on Rio 2016.
"""

from __future__ import annotations

from dataclasses import replace
from itertools import product

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Lasso, LinearRegression, LogisticRegression, PoissonRegressor, Ridge
from sklearn.metrics import accuracy_score, f1_score
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from sklearn.svm import SVC, SVR

from .config import ECONOMIC_HISTORICAL_FEATURES, TARGET, ExperimentConfig, ForestParams, ModelSpec
from .models import MedalForecaster, regression_metrics

FEATURES = tuple(ECONOMIC_HISTORICAL_FEATURES)  # the paper's information set: history + World Bank

# Heavy-tailed counts are log-transformed before linear and kernel models.
COUNT_FEATURES = ("Previous_Medals", "Previous_Gold", "Previous_Athletes", "Previous_Sports",
                  "Previous_Events", "Rolling_3_Medal_Avg")


def preprocessor(features: tuple[str, ...] = FEATURES) -> Pipeline:
    """log1p on counts -> median imputation (+ missing flags) -> standardisation."""
    counts = [f for f in features if f in COUNT_FEATURES]
    rest = [f for f in features if f not in COUNT_FEATURES]
    logs = ColumnTransformer(
        [("log_counts", FunctionTransformer(np.log1p, feature_names_out="one-to-one"), counts),
         ("other", "passthrough", rest)],
        verbose_feature_names_out=False,
    )
    return make_pipeline(logs, SimpleImputer(strategy="median", add_indicator=True), StandardScaler())


def regressor_grid(forest: ForestParams) -> dict[str, tuple[object, dict[str, tuple], bool]]:
    """name -> (estimator, hyper-parameter grid, supports the momentum target)."""
    pre = preprocessor()
    return {
        "Linear Regression": (make_pipeline(pre, LinearRegression()), {}, True),
        "Ridge": (make_pipeline(pre, Ridge()), {"ridge__alpha": (0.1, 1.0, 10.0, 100.0)}, True),
        "Lasso": (make_pipeline(pre, Lasso(max_iter=20000)), {"lasso__alpha": (0.001, 0.01, 0.1, 1.0)}, True),
        # Poisson needs a non-negative target, so it only predicts counts.
        "Poisson Regression": (make_pipeline(pre, PoissonRegressor(max_iter=2000)),
                               {"poissonregressor__alpha": (0.01, 0.1, 1.0)}, False),
        "SVR (RBF kernel)": (make_pipeline(pre, SVR()),
                             {"svr__C": (1.0, 10.0, 100.0), "svr__epsilon": (0.05, 0.5)}, True),
        "Random Forest": (RandomForestRegressor(**forest.as_dict()), {}, True),
    }


def classifier_grid(forest: ForestParams) -> dict[str, object]:
    pre = preprocessor()
    clf_params = {k: v for k, v in forest.as_dict().items() if k != "max_features"}
    return {
        "Logistic Regression": make_pipeline(pre, LogisticRegression(max_iter=2000)),
        "SVM (RBF kernel)": make_pipeline(pre, SVC()),
        "Gaussian Naive Bayes": make_pipeline(pre, GaussianNB()),
        "Multilayer Perceptron": make_pipeline(pre, MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=2000,
                                                                   early_stopping=True, random_state=forest.random_state)),
        "Random Forest": RandomForestClassifier(**clf_params),
    }


class NaiveBayesRidgeHurdle(BaseEstimator, RegressorMixin):
    """The paper's best design: Gaussian Naive Bayes decides medal / no medal,
    then Ridge regression (trained on medal-winning rows only) predicts how many.

    ``target="momentum"`` swaps the Ridge stage to our momentum target
    (log-change versus the previous Games). Inputs are the raw feature frame
    and raw medal counts.
    """

    def __init__(self, alpha: float = 1.0, target: str = "level"):
        self.alpha = alpha
        self.target = target

    def _encode(self, X: pd.DataFrame, y: np.ndarray) -> np.ndarray:
        if self.target == "momentum":
            return np.log1p(y) - np.log1p(X["Previous_Medals"].to_numpy(dtype=float))
        return y

    def _decode(self, X: pd.DataFrame, raw: np.ndarray) -> np.ndarray:
        if self.target == "momentum":
            raw = np.expm1(np.log1p(X["Previous_Medals"].to_numpy(dtype=float)) + raw)
        return np.clip(raw, 0.0, None)

    def fit(self, X: pd.DataFrame, y) -> "NaiveBayesRidgeHurdle":
        X = X[list(FEATURES)]
        y = np.asarray(y, dtype=float)
        won = y > 0
        self.classifier_ = make_pipeline(preprocessor(), GaussianNB()).fit(X, won)
        self.regressor_ = make_pipeline(preprocessor(), Ridge(alpha=self.alpha)).fit(
            X[won], self._encode(X[won], y[won]))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = X[list(FEATURES)]
        wins = self.classifier_.predict(X).astype(bool)
        return np.where(wins, self._decode(X, self.regressor_.predict(X)), 0.0)


PAPER_BEST = "Paper best: Naive Bayes + Ridge"


def _games(df: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    return df.loc[df["Year"].between(start, end)]


def _forecaster(estimator, target: str) -> MedalForecaster:
    spec = ModelSpec(name="zoo", features=FEATURES, target=target)
    return MedalForecaster(spec, estimator=estimator)


def compare_regressors(df: pd.DataFrame, config: ExperimentConfig, forest: ForestParams) -> pd.DataFrame:
    split = config.split
    tune_train = _games(df, split.train_start, split.train_end)
    valid = _games(df, split.validation_year, split.validation_year)
    final_train = _games(df, split.train_start, split.validation_year)
    test = _games(df, split.test_year, split.test_year)

    rows = []
    for name, (estimator, grid, momentum_ok) in regressor_grid(forest).items():
        for target in ("level", "momentum"):
            if target == "momentum" and not momentum_ok:
                continue
            best_params, best_mae = {}, np.inf
            for values in product(*grid.values()) if grid else [()]:
                params = dict(zip(grid.keys(), values))
                model = _forecaster(clone(estimator).set_params(**params), target).fit(tune_train, tune_train[TARGET])
                mae = regression_metrics(valid[TARGET], model.predict(valid))["MAE"]
                if mae < best_mae:
                    best_params, best_mae = params, mae
            model = _forecaster(clone(estimator).set_params(**best_params), target).fit(final_train, final_train[TARGET])
            rows.append({"model": name, "target": "Momentum" if target == "momentum" else "Count",
                         "validation_MAE": best_mae, "params": best_params,
                         **regression_metrics(test[TARGET], model.predict(test))})

    # The paper's best two-stage pairing, with its count target and with ours.
    for target in ("level", "momentum"):
        best_alpha, best_mae = None, np.inf
        for alpha in (0.1, 1.0, 10.0, 100.0):
            model = NaiveBayesRidgeHurdle(alpha, target).fit(tune_train, tune_train[TARGET])
            mae = regression_metrics(valid[TARGET], model.predict(valid))["MAE"]
            if mae < best_mae:
                best_alpha, best_mae = alpha, mae
        model = NaiveBayesRidgeHurdle(best_alpha, target).fit(final_train, final_train[TARGET])
        rows.append({"model": PAPER_BEST, "target": "Momentum" if target == "momentum" else "Count",
                     "validation_MAE": best_mae, "params": {"alpha": best_alpha},
                     **regression_metrics(test[TARGET], model.predict(test))})
    return pd.DataFrame(rows)


def compare_classifiers(df: pd.DataFrame, config: ExperimentConfig, forest: ForestParams) -> pd.DataFrame:
    """Medal / no-medal classification, as in the paper's first stage."""
    split = config.split
    X_cols = list(FEATURES)
    rows = []
    for name, clf in classifier_grid(forest).items():
        scores = {}
        for label, (train_end, year) in {"2012": (split.train_end, split.validation_year),
                                         "2016": (split.validation_year, split.test_year)}.items():
            train, test = _games(df, split.train_start, train_end), _games(df, year, year)
            model = clone(clf).fit(train[X_cols], train[TARGET] > 0)
            pred = model.predict(test[X_cols])
            scores[f"accuracy_{label}"] = accuracy_score(test[TARGET] > 0, pred)
            scores[f"f1_{label}"] = f1_score(test[TARGET] > 0, pred)
        rows.append({"model": name, **scores})

    # Reference rule: predict a medal exactly when the country medalled last Games.
    rule = {"model": "Rule: medalled last Games"}
    for label, year in {"2012": split.validation_year, "2016": split.test_year}.items():
        test = _games(df, year, year)
        won, guess = test[TARGET] > 0, test["Previous_Medals"] > 0
        rule[f"accuracy_{label}"] = accuracy_score(won, guess)
        rule[f"f1_{label}"] = f1_score(won, guess)
    rows.append(rule)
    return pd.DataFrame(rows)


def run_model_zoo(df: pd.DataFrame, config: ExperimentConfig, forest: ForestParams) -> dict[str, pd.DataFrame]:
    forest = replace(forest, random_state=config.forest.random_state)
    return {"regressors": compare_regressors(df, config, forest),
            "classifiers": compare_classifiers(df, config, forest)}
