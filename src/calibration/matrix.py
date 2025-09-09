from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

import pandas as pd

from core.dates import fiscal_year


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


