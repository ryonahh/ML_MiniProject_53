"""Project-wide configuration: paths, temporal splits, feature sets and models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RESULTS_DIR = PROJECT_ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
SITE_DATA_PATH = PROJECT_ROOT / "docs" / "assets" / "data.js"

ATHLETE_EVENTS_CSV = RAW_DIR / "athlete_events.csv"
NOC_REGIONS_CSV = RAW_DIR / "noc_regions.csv"
# Six World Bank indicators extracted by scripts/prepare_world_bank.py.
WORLD_BANK_CSV = PROJECT_ROOT / "data" / "external" / "world_bank_indicators.csv"
# Real Tokyo 2020 results, used only to score the 2020 forecast after the fact.
TOKYO_ACTUALS_CSV = PROJECT_ROOT / "data" / "external" / "tokyo2020_medals.csv"
DATA_SOURCE_URL = "https://raw.githubusercontent.com/rgriff23/Olympic_history/master/data"

TARGET = "Total_Medals"
RANDOM_STATE = 42

# Feature sets -------------------------------------------------------------
# Every feature is computed only from Games *before* the target Games, so each
# model sees exactly the information that existed when a forecast is made.
BASELINE_FEATURES: list[str] = ["Previous_Medals", "Previous_Gold"]

HISTORICAL_FEATURES: list[str] = BASELINE_FEATURES + [
    "Previous_Athletes",
    "Previous_Sports",
    "Previous_Events",
    "Historical_Medal_Growth",
    "Historical_Athlete_Growth",
    "Rolling_3_Medal_Avg",
    "Medal_Efficiency",
]

# World Bank indicators (the reference paper's socioeconomic inputs), from the year before the Games.
ECONOMIC_FEATURES: list[str] = [
    "Log_GDP", "Log_GDP_Per_Capita", "GDP_Growth", "Log_Population",
    "Population_Growth", "Log_Land_Area", "World_GDP_Share", "World_Population_Share",
]
ECONOMIC_HISTORICAL_FEATURES: list[str] = HISTORICAL_FEATURES + ECONOMIC_FEATURES

MOMENTUM_SCORE = "Performance_Momentum"
MOMENTUM_FEATURES: list[str] = HISTORICAL_FEATURES + [MOMENTUM_SCORE]

# The three signals blended into the Performance Momentum score.
MOMENTUM_COMPONENTS: list[str] = [
    "Historical_Medal_Growth",
    "Historical_Athlete_Growth",
    "Medal_Efficiency",
]


@dataclass(frozen=True)
class ModelSpec:
    """One experimental arm: which features, which target, which learner.

    ``target`` is either ``"level"`` (predict the medal count directly) or
    ``"momentum"`` (predict the log-change versus the previous Games and add
    it back to the previous count - the project's proposed formulation).
    """

    name: str
    features: tuple[str, ...]
    target: str = "level"
    learner: str = "forest"  # "forest" or "two_stage"
    description: str = ""


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        "Baseline", tuple(BASELINE_FEATURES),
        description="Previous medals and golds only.",
    ),
    ModelSpec(
        "Historical Features", tuple(HISTORICAL_FEATURES),
        description="Adds participation scale, trends, rolling average and efficiency.",
    ),
    ModelSpec(
        "Historical + Momentum Score", tuple(MOMENTUM_FEATURES),
        description="Adds the composite Performance Momentum score as one more feature.",
    ),
    ModelSpec(
        "Historical + Economic", tuple(ECONOMIC_HISTORICAL_FEATURES),
        description="Adds the paper's World Bank indicators (GDP, population, land area, shares).",
    ),
    ModelSpec(
        "Paper Two-Stage", tuple(ECONOMIC_HISTORICAL_FEATURES), learner="two_stage",
        description="Reference-paper design on its inputs: medal / no-medal classifier, then a regressor.",
    ),
    ModelSpec(
        "Momentum Target", tuple(HISTORICAL_FEATURES), target="momentum",
        description="Proposed: learn the change in medals relative to the previous Games.",
    ),
    ModelSpec(
        "Momentum Target + Score", tuple(MOMENTUM_FEATURES), target="momentum",
        description="Proposed target with the momentum score added as a feature.",
    ),
    ModelSpec(
        "Momentum Target + Economic", tuple(ECONOMIC_HISTORICAL_FEATURES), target="momentum",
        description="Proposed target with the paper's World Bank indicators added.",
    ),
)

PROPOSED_MODEL = "Momentum Target"
REFERENCE_MODEL = "Historical Features"


@dataclass(frozen=True)
class TemporalSplit:
    """Chronological split: fit on the past, tune on one Games, test on the next."""

    train_start: int = 1964
    train_end: int = 2008
    validation_year: int = 2012
    test_year: int = 2016
    forecast_year: int = 2020


@dataclass(frozen=True)
class ForestParams:
    """Random Forest settings shared by every model (only features/target change)."""

    n_estimators: int = 300
    min_samples_leaf: int = 5
    max_features: float = 0.6
    random_state: int = RANDOM_STATE
    n_jobs: int = -1

    def as_dict(self) -> dict:
        return dict(self.__dict__)


# Small grid searched on the 2012 validation Games; one setting is shared by
# all models so that differences in score come from features and targets.
FOREST_GRID: dict[str, tuple] = {
    "min_samples_leaf": (1, 3, 5, 10),
    "max_features": (0.6, 1.0),
}


@dataclass(frozen=True)
class ExperimentConfig:
    split: TemporalSplit = field(default_factory=TemporalSplit)
    forest: ForestParams = field(default_factory=ForestParams)
    rolling_origin_years: tuple[int, ...] = (1996, 2000, 2004, 2008, 2012, 2016)
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4)
    bootstrap_samples: int = 2000
