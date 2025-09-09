from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

import pandas as pd

from core.dates import fiscal_year
from macro.config import load_macro_yaml


INTEREST_CATEGORY_KEEP = "INTEREST EXPENSE ON PUBLIC ISSUES"


def find_latest_interest_file(pattern: str = "input/IntExp_*") -> Path:
    paths = sorted(Path().glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No files matched pattern: {pattern}")
    # Prefer CSV if mixed types; otherwise, pick newest by mtime
    csvs = [p for p in paths if p.suffix.lower() == ".csv"]
    candidates = csvs if csvs else paths
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _assign_debt_category(expense_type: str) -> str:
    t = (expense_type or "").lower()
    # TIPS and inflation compensation
    if "inflation" in t or "tips" in t:
        return "TIPS"
    # Domestic/Foreign/State&Local/misc buckets treated as OTHER
    other_keywords = [
        "domestic series",
        "foreign series",
        "state & local",
        "state and local",
        "matured debt",
        "demand deposits",
        "c/i",
        "rea series",
    ]
    if any(k in t for k in other_keywords):
        return "OTHER"
    # Bills
    if "bill" in t:
        return "SHORT"
    # Notes/Bonds/FRN → NB
    if "note" in t or "bond" in t or "floating rate" in t or "frn" in t:
        return "NB"
    # Fallback
    return "OTHER"


def load_interest_raw(path: Path) -> pd.DataFrame:
    df = _read_any(path)
    # Standardize column names
    required_cols = {
        "Record Date": "Record Date",
        "Expense Category Description": "Expense Category Description",
        "Expense Group Description": "Expense Group Description",
        "Expense Type Description": "Expense Type Description",
        "Current Month Expense Amount": "Current Month Expense Amount",
    }
    for k in required_cols:
        if k not in df.columns:
            raise ValueError(f"Missing required column: {k}")

    # Filter to interest on public issues only
    df = df[df["Expense Category Description"] == INTEREST_CATEGORY_KEEP].copy()

    # Parse dates and derive CY/FY/Month
    df["Record Date"] = pd.to_datetime(df["Record Date"])  # month-end in input
    df["Calendar Year"] = df["Record Date"].dt.year
    df["Fiscal Year"] = df["Record Date"].apply(lambda d: fiscal_year(pd.Timestamp(d)))
    df["Month"] = df["Record Date"].dt.month

    # Map debt category
    df["Debt Category"] = df["Expense Type Description"].astype(str).map(_assign_debt_category)

    # Normalize to USD millions
    df["Interest Expense"] = pd.to_numeric(df["Current Month Expense Amount"], errors="coerce") / 1e6

    # Keep only relevant columns in raw for downstream aggregations
    return df[
        [
            "Record Date",
            "Calendar Year",
            "Fiscal Year",
            "Month",
            "Debt Category",
            "Interest Expense",
        ]
    ].copy()


def build_monthly_by_category(df: pd.DataFrame) -> pd.DataFrame:
    # Truncate to month start for grouping label
    month_start = df["Record Date"].dt.to_period("M").dt.to_timestamp()
    g = (
        df.assign(**{"Record Date": month_start})
        .groupby(["Record Date", "Calendar Year", "Fiscal Year", "Month", "Debt Category"], as_index=False)[
            "Interest Expense"
        ]
        .sum()
        .sort_values("Record Date")
    )
    return g


def build_fy_totals(df_monthly_by_cat: pd.DataFrame) -> pd.DataFrame:
    return (
        df_monthly_by_cat.groupby(["Fiscal Year"], as_index=False)["Interest Expense"].sum()
        .rename(columns={"Interest Expense": "Interest Expense"})
        .sort_values("Fiscal Year")
    )


def build_cy_totals(df_monthly_by_cat: pd.DataFrame) -> pd.DataFrame:
    return (
        df_monthly_by_cat.groupby(["Calendar Year"], as_index=False)["Interest Expense"].sum()
        .rename(columns={"Interest Expense": "Interest Expense"})
        .sort_values("Calendar Year")
    )


def write_interest_diagnostics(
    monthly_by_category: pd.DataFrame,
    fy_totals: pd.DataFrame,
    cy_totals: pd.DataFrame,
    out_dir: Path | str = "output/diagnostics",
) -> Tuple[Path, Path, Path]:
    out_base = Path(out_dir)
    out_base.mkdir(parents=True, exist_ok=True)
    p1 = out_base / "interest_monthly_by_category.csv"
    p2 = out_base / "interest_fy_totals.csv"
    p3 = out_base / "interest_cy_totals.csv"
    monthly_by_category.to_csv(p1, index=False)
    fy_totals.to_csv(p2, index=False)
    cy_totals.to_csv(p3, index=False)
    return p1, p2, p3


def _load_y_from_interest_by_category(path: Path | str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Record Date"])
    # y excludes OTHER: sum across SHORT, NB, TIPS
    keep = df[df["Debt Category"].isin(["SHORT", "NB", "TIPS"])]
    y = (
        keep.groupby(["Record Date"], as_index=False)["Interest Expense"].sum()
        .rename(columns={"Interest Expense": "y"})
        .sort_values("Record Date")
    )
    return y


def _load_stocks(path: Path | str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Record Date"])  # expects stock_short, stock_nb, stock_tips
    df = df.sort_values("Record Date")
    return df[["Record Date", "stock_short", "stock_nb", "stock_tips"]]


def build_calibration_matrix(
    interest_by_category_path: Path | str = "output/diagnostics/interest_monthly_by_category.csv",
    stocks_path: Path | str = "output/diagnostics/outstanding_by_bucket_scaled.csv",
    config_path: Path | str = "input/macro.yaml",
    window_months: int = 48,
) -> pd.DataFrame:
    """
    Build calibration matrix with columns: Record Date, y, SHORT, NB, TIPS over the last window_months.
    X columns are stock_k * (rate_k/12) using rates from macro.yaml; y excludes OTHER.
    """
    y = _load_y_from_interest_by_category(interest_by_category_path)
    stocks = _load_stocks(stocks_path)

    # Align by month period to handle month-start vs month-end conventions
    y["_month"] = y["Record Date"].dt.to_period("M")
    stocks["_month"] = stocks["Record Date"].dt.to_period("M")
    stocks = stocks.drop(columns=["Record Date"]).rename(columns={"_month": "_month_stocks"})
    merged = y.merge(stocks, left_on="_month", right_on="_month_stocks", how="inner")
    merged = merged.drop(columns=["_month_stocks"]).rename(columns={"_month": "Month"})
    merged = merged.sort_values("Month").reset_index(drop=True)
    # Convert period to month-start timestamp for output consistency
    merged["Record Date"] = merged["Month"].apply(lambda p: p.to_timestamp())
    if len(merged) == 0:
        raise ValueError("No overlapping dates between interest and stocks")

    # Take last window
    merged = merged.tail(window_months).copy()

    # Rates from config (annualized); convert to monthly
    cfg = load_macro_yaml(config_path)
    if cfg.rates_constant is None:
        raise ValueError("rates in macro.yaml must be provided (type: constant)")
    r_short, r_nb, r_tips = cfg.rates_constant
    m_short = r_short / 12.0
    m_nb = r_nb / 12.0
    m_tips = r_tips / 12.0

    # Build X as monthly interest proxies from stocks
    merged["SHORT"] = merged["stock_short"] * m_short
    merged["NB"] = merged["stock_nb"] * m_nb
    merged["TIPS"] = merged["stock_tips"] * m_tips

    mat = merged[["Record Date", "y", "SHORT", "NB", "TIPS"]].copy()

    # Validations
    if mat[["y", "SHORT", "NB", "TIPS"]].isna().any().any():
        raise ValueError("NaNs found in calibration matrix")
    if mat["NB"].var() <= 0:
        raise ValueError("NB variance must be > 0 for identifiability")

    # Write artifact
    out = Path("output/diagnostics/calibration_matrix.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    mat.to_csv(out, index=False)
    return mat

