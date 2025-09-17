from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from core.dates import fiscal_year
from macro.gdp import GDPModel


def annualize(monthly_df: pd.DataFrame, gdp_model: GDPModel) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Annualize monthly interest to CY and FY levels and compute % of GDP.

    monthly_df must have index 'date' (MS) and column 'interest_total'.
    Returns (cy_df, fy_df) with columns: year, interest, gdp, pct_gdp.
    If optional columns exist in monthly_df (e.g., 'additional_revenue'),
    they are summed to annual frequency and included as additional columns.
    """
    if "interest_total" not in monthly_df.columns:
        raise ValueError("monthly_df must contain 'interest_total'")
    # Normalize index name
    if monthly_df.index.name != "date":
        monthly_df = monthly_df.copy()
        monthly_df.index.name = "date"

    df = monthly_df.copy()
    df.index = pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp()
    df["CY"] = df.index.year
    df["FY"] = df.index.map(fiscal_year)

    cy = df.groupby("CY", as_index=False)["interest_total"].sum().rename(columns={"CY": "year", "interest_total": "interest"})
    fy = df.groupby("FY", as_index=False)["interest_total"].sum().rename(columns={"FY": "year", "interest_total": "interest"})

    # Optionally aggregate additional revenue if present
    if "additional_revenue" in df.columns:
        cy_add = df.groupby("CY", as_index=False)["additional_revenue"].sum().rename(columns={"CY": "year"})
        fy_add = df.groupby("FY", as_index=False)["additional_revenue"].sum().rename(columns={"FY": "year"})
        cy = cy.merge(cy_add, on="year", how="left")
        fy = fy.merge(fy_add, on="year", how="left")

    def _with_gdp(table: pd.DataFrame, frame: str) -> pd.DataFrame:
        out = table.copy()
        if frame == "CY":
            out["gdp"] = out["year"].map(gdp_model.gdp_cy)
        else:
            out["gdp"] = out["year"].map(gdp_model.gdp_fy)
        out["pct_gdp"] = out["interest"] / out["gdp"]
        return out

    return _with_gdp(cy, "CY"), _with_gdp(fy, "FY")


def write_annual_csvs(cy_df: pd.DataFrame, fy_df: pd.DataFrame, base_dir: str = "output") -> Tuple[Path, Path]:
    p_cy = Path(base_dir) / "calendar_year" / "spreadsheets" / "annual.csv"
    p_fy = Path(base_dir) / "fiscal_year" / "spreadsheets" / "annual.csv"
    p_cy.parent.mkdir(parents=True, exist_ok=True)
    p_fy.parent.mkdir(parents=True, exist_ok=True)
    cy_df.to_csv(p_cy, index=False)
    fy_df.to_csv(p_fy, index=False)
    return p_cy, p_fy


