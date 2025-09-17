from __future__ import annotations

from pathlib import Path
from typing import Tuple, Optional, Dict

import pandas as pd

from core.dates import fiscal_year
from macro.gdp import GDPModel
from macro.config import MacroConfig


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


def _fill_year_map(values: Dict[int, float], years_needed: list[int]) -> Dict[int, float]:
    if not values:
        return {y: float("nan") for y in years_needed}
    filled: Dict[int, float] = {}
    sorted_years = sorted(set([*years_needed, *values.keys()]))
    current = values.get(min(values.keys()), float("nan"))
    for y in sorted_years:
        if y in values:
            current = float(values[y])
        filled[y] = current
    return {y: filled[y] for y in years_needed}


def write_overview_csvs(
    revenue_month: pd.Series,
    outlays_month: pd.Series,
    additional_month: Optional[pd.Series],
    monthly_df: pd.DataFrame,
    gdp_model: GDPModel,
    cfg: MacroConfig,
    *,
    base_dir: str = "output",
) -> Tuple[Path, Path]:
    """
    Write overview.csv for CY and FY with:
      year, gdp_usd_bn, gdp_growth_pct, revenue_usd_bn, revenue_pct_gdp,
      primary_outlays_usd_bn, primary_outlays_pct_gdp, primary_deficit_usd_bn,
      primary_deficit_pct_gdp, additional_revenue_usd_bn, additional_revenue_pct_gdp,
      interest_expense_usd_bn, interest_expense_pct_gdp, effective_interest_rate_pct,
      pce_inflation_pct

    Sums are based on projection months present in monthly_df.
    """
    # Normalize monthly index
    df = monthly_df.copy()
    if df.index.name != "date":
        df.index = pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp()
        df.index.name = "date"
    else:
        df.index = pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp()

    # Interest should align with annual.csv which uses interest_total only.
    # Do NOT add other_interest here to avoid double-counting versus annual.csv.
    interest_m = df["interest_total"].astype(float)

    # Total stock per month (marketable)
    stock_m = df[["stock_short", "stock_nb", "stock_tips"]].sum(axis=1).astype(float)

    # Series alignment to monthly index
    rev_m = revenue_month.reindex(df.index).fillna(0.0).astype(float)
    out_m = outlays_month.reindex(df.index).fillna(0.0).astype(float)
    add_m = (additional_month.reindex(df.index).fillna(0.0).astype(float)) if additional_month is not None else pd.Series(0.0, index=df.index)

    # PCE inflation mapping (percent)
    pce_map = {int(k): float(v) for k, v in (getattr(cfg, "inflation_pce", {}) or {}).items()}

    def _build_table(frame: str) -> pd.DataFrame:
        if frame not in {"CY", "FY"}:
            raise ValueError("frame must be 'CY' or 'FY'")
        if frame == "FY":
            years = sorted(set(df.index.map(fiscal_year)))
            get_gdp = lambda y: float(gdp_model.gdp_fy(int(y)))
            year_of = lambda d: int(fiscal_year(d))
        else:
            years = sorted(set(df.index.year))
            get_gdp = lambda y: float(gdp_model.gdp_cy(int(y)))
            year_of = lambda d: int(pd.Timestamp(d).year)

        # Annual sums per year
        rows = []
        # Precompute PCE per requested years (carry forward/back)
        pce_filled = _fill_year_map(pce_map, years)
        for y in years:
            mask = df.index.map(year_of) == int(y)
            if not mask.any():
                continue
            gdp_y = get_gdp(int(y))
            gdp_prev = get_gdp(int(y) - 1) if (int(y) - 1) in years or True else float("nan")
            # Growth based on model levels
            gdp_growth_pct = ((gdp_y / gdp_prev - 1.0) * 100.0) if (pd.notna(gdp_prev) and gdp_prev not in (0.0,)) else float("nan")

            rev_y = float(rev_m.loc[mask].sum())
            out_y = float(out_m.loc[mask].sum())
            add_y = float(add_m.loc[mask].sum())
            prim_def_y = out_y - rev_y - add_y
            int_y = float(interest_m.loc[mask].sum())
            stock_avg = float(stock_m.loc[mask].mean()) if mask.any() else float("nan")
            eff_rate = (int_y / stock_avg) if (pd.notna(stock_avg) and stock_avg not in (0.0,)) else float("nan")

            # Convert to billions and percents
            def to_bn(x: float) -> float:
                return float(x) / 1_000.0 if pd.notna(x) else float("nan")

            row = {
                "year": int(y),
                "gdp_usd_bn": to_bn(gdp_y),
                "gdp_growth_pct": float(round(gdp_growth_pct, 2)) if pd.notna(gdp_growth_pct) else float("nan"),
                "revenue_usd_bn": float(round(to_bn(rev_y), 1)),
                "revenue_pct_gdp": float(round((rev_y / gdp_y) * 100.0, 2)) if gdp_y not in (0.0,) else 0.0,
                "primary_outlays_usd_bn": float(round(to_bn(out_y), 1)),
                "primary_outlays_pct_gdp": float(round((out_y / gdp_y) * 100.0, 2)) if gdp_y not in (0.0,) else 0.0,
                "primary_deficit_usd_bn": float(round(to_bn(prim_def_y), 1)),
                "primary_deficit_pct_gdp": float(round((prim_def_y / gdp_y) * 100.0, 2)) if gdp_y not in (0.0,) else 0.0,
                "additional_revenue_usd_bn": float(round(to_bn(add_y), 1)),
                "additional_revenue_pct_gdp": float(round((add_y / gdp_y) * 100.0, 2)) if gdp_y not in (0.0,) else 0.0,
                "interest_expense_usd_bn": float(round(to_bn(int_y), 1)),
                "interest_expense_pct_gdp": float(round((int_y / gdp_y) * 100.0, 2)) if gdp_y not in (0.0,) else 0.0,
                "effective_interest_rate_pct": float(round(eff_rate * 100.0, 2)) if pd.notna(eff_rate) else float("nan"),
                "pce_inflation_pct": float(round(float(pce_filled.get(int(y), float("nan"))), 2)) if pce_filled else float("nan"),
            }
            rows.append(row)

        out = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
        return out

    cy_table = _build_table("CY")
    fy_table = _build_table("FY")

    # Write CSVs
    p_cy = Path(base_dir) / "calendar_year" / "spreadsheets" / "overview.csv"
    p_fy = Path(base_dir) / "fiscal_year" / "spreadsheets" / "overview.csv"
    p_cy.parent.mkdir(parents=True, exist_ok=True)
    p_fy.parent.mkdir(parents=True, exist_ok=True)
    cy_table.to_csv(p_cy, index=False)
    fy_table.to_csv(p_fy, index=False)
    return p_cy, p_fy

