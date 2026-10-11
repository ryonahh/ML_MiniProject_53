"""Loading, cleaning and aggregating the raw athlete-level Olympic records.

The raw file has one row per athlete per event, so a gold in the men's 4x100m
relay appears four times. Official medal tables count it once, so medals are
de-duplicated per (NOC, Games, Event, Medal) before they are aggregated.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pandas as pd

from .config import ATHLETE_EVENTS_CSV, DATA_SOURCE_URL, NOC_REGIONS_CSV, RAW_DIR

# NOC codes whose region is missing or inconsistent in noc_regions.csv.
REGION_FIXES: dict[str, str] = {
    "SGP": "Singapore",  # athlete file uses SGP, region file uses SIN
    "ROT": "Refugee Olympic Team",
    "TUV": "Tuvalu",
    "UNK": "Unknown",
}

# Host nation of each Summer Games, expressed with noc_regions.csv names.
HOSTS: dict[int, str] = {
    1964: "Japan", 1968: "Mexico", 1972: "Germany", 1976: "Canada",
    1980: "Russia", 1984: "USA", 1988: "South Korea", 1992: "Spain",
    1996: "USA", 2000: "Australia", 2004: "Greece", 2008: "China",
    2012: "UK", 2016: "Brazil", 2020: "Japan",
}

# 1906 "Intercalated Games" are not recognised by the IOC.
EXCLUDED_YEARS = {1906}


def download_raw_data(target_dir: Path = RAW_DIR, overwrite: bool = False) -> None:
    """Fetch the Kaggle "120 years of Olympic history" CSVs from the author's GitHub."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ("athlete_events.csv", "noc_regions.csv"):
        destination = target_dir / name
        if destination.exists() and not overwrite:
            continue
        print(f"Downloading {name} ...")
        urllib.request.urlretrieve(f"{DATA_SOURCE_URL}/{name}", destination)


def load_raw(
    athletes_path: Path = ATHLETE_EVENTS_CSV, regions_path: Path = NOC_REGIONS_CSV
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not athletes_path.exists() or not regions_path.exists():
        download_raw_data(athletes_path.parent)
    return pd.read_csv(athletes_path), pd.read_csv(regions_path)


def clean_summer_games(athletes: pd.DataFrame, regions: pd.DataFrame) -> pd.DataFrame:
    """Keep Summer Games only and attach a stable country (region) to every row.

    Mapping NOC -> region merges historical delegations into one country
    (e.g. FRG/GDR -> Germany, URS/EUN -> Russia), which gives every country a
    continuous history to learn from.
    """
    summer = athletes.loc[
        (athletes["Season"] == "Summer") & ~athletes["Year"].isin(EXCLUDED_YEARS)
    ].copy()

    region_map = regions.set_index("NOC")["region"].to_dict()
    region_map.update(REGION_FIXES)
    summer["Country"] = summer["NOC"].map(region_map).fillna(summer["Team"])
    return summer


def aggregate_country_year(summer: pd.DataFrame) -> pd.DataFrame:
    """Collapse athlete rows into one row per Country x Olympic Year."""
    participation = summer.groupby(["Country", "Year"]).agg(
        Athletes=("ID", "nunique"),
        Sports=("Sport", "nunique"),
        Events=("Event", "nunique"),
    )

    medals = (
        summer.dropna(subset=["Medal"])
        .drop_duplicates(subset=["NOC", "Games", "Event", "Medal"])
        .groupby(["Country", "Year", "Medal"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["Gold", "Silver", "Bronze"], fill_value=0)
    )

    table = participation.join(medals, how="left").fillna(0)
    table[["Gold", "Silver", "Bronze"]] = table[["Gold", "Silver", "Bronze"]].astype(int)
    table["Total_Medals"] = table[["Gold", "Silver", "Bronze"]].sum(axis=1)
    table = table.reset_index().sort_values(["Country", "Year"], ignore_index=True)
    table["Is_Host"] = (table["Country"] == table["Year"].map(HOSTS)).astype(int)
    return table


def build_country_year_table() -> pd.DataFrame:
    """End-to-end: raw CSVs -> tidy Country x Year medal and participation table."""
    athletes, regions = load_raw()
    return aggregate_country_year(clean_summer_games(athletes, regions))
