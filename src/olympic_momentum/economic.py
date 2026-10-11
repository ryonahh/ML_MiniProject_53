"""World Bank socioeconomic features, joined without look-ahead.

For the Games held in year *t* every indicator is taken from year *t - 1*, the
latest value that existed before the Games began. Shares of the world total
are computed within that same year.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ECONOMIC_FEATURES, WORLD_BANK_CSV

# WDI series code -> column name (the indicators used in the reference paper).
WDI_INDICATORS: dict[str, str] = {
    "NY.GDP.MKTP.CD": "GDP",
    "NY.GDP.PCAP.CD": "GDP_Per_Capita",
    "NY.GDP.MKTP.KD.ZG": "GDP_Growth",
    "SP.POP.TOTL": "Population",
    "SP.POP.GROW": "Population_Growth",
    "AG.LND.TOTL.K2": "Land_Area",
}

# Olympic (noc_regions.csv) names whose World Bank name differs.
NAME_TO_ISO3: dict[str, str] = {
    "Antigua": "ATG", "Bahamas": "BHS", "Boliva": "BOL", "Brunei": "BRN", "Cape Verde": "CPV",
    "Curacao": "CUW", "Czech Republic": "CZE", "Democratic Republic of the Congo": "COD",
    "Egypt": "EGY", "Gambia": "GMB", "Iran": "IRN", "Ivory Coast": "CIV", "Kyrgyzstan": "KGZ",
    "Laos": "LAO", "Macedonia": "MKD", "Micronesia": "FSM", "Nauru": "NRU", "North Korea": "PRK",
    "Palestine": "PSE", "Puerto Rico": "PRI", "Republic of Congo": "COG", "Russia": "RUS",
    "Saint Kitts": "KNA", "Saint Lucia": "LCA", "Saint Vincent": "VCT",
    "Sao Tome and Principe": "STP", "Slovakia": "SVK", "Somalia": "SOM", "South Korea": "KOR",
    "Swaziland": "SWZ", "Syria": "SYR", "Trinidad": "TTO", "Turkey": "TUR", "UK": "GBR",
    "USA": "USA", "Venezuela": "VEN", "Vietnam": "VNM", "Virgin Islands, British": "VGB",
    "Virgin Islands, US": "VIR", "Yemen": "YEM",
}


def olympic_to_iso3(wdi_countries: pd.DataFrame) -> dict[str, str]:
    """Olympic country name -> ISO3, using WDI table names plus the manual fixes above."""
    mapping = dict(zip(wdi_countries["Table Name"], wdi_countries["Country Code"]))
    mapping.update(NAME_TO_ISO3)
    return mapping


def load_world_bank(path: Path = WORLD_BANK_CSV) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, comment="#")


def economic_indicators(world_bank: pd.DataFrame) -> pd.DataFrame:
    """Derived features per Country x calendar year (logs and world shares)."""
    wb = world_bank.copy()
    out = wb[["Country", "Year"]].copy()
    out["Log_GDP"] = np.log(wb["GDP"])
    out["Log_GDP_Per_Capita"] = np.log(wb["GDP_Per_Capita"])
    out["GDP_Growth"] = wb["GDP_Growth"]
    out["Log_Population"] = np.log(wb["Population"])
    out["Population_Growth"] = wb["Population_Growth"]
    out["Log_Land_Area"] = np.log(wb["Land_Area"])
    out["World_GDP_Share"] = 100 * wb["GDP"] / wb.groupby("Year")["GDP"].transform("sum")
    out["World_Population_Share"] = 100 * wb["Population"] / wb.groupby("Year")["Population"].transform("sum")
    return out


def add_economic_features(df: pd.DataFrame, world_bank: pd.DataFrame | None = None) -> pd.DataFrame:
    """Join indicators from the year *before* each Games. Missing values stay NaN.

    Random Forests in scikit-learn handle NaN natively; the linear and kernel
    models impute inside their own pipelines (fitted on training rows only).
    """
    world_bank = load_world_bank() if world_bank is None else world_bank
    if world_bank is None:
        return df.assign(**{c: np.nan for c in ECONOMIC_FEATURES})
    indicators = economic_indicators(world_bank)
    indicators["Year"] = indicators["Year"] + 1  # value from t-1 is used for Games in year t
    return df.merge(indicators, on=["Country", "Year"], how="left")
