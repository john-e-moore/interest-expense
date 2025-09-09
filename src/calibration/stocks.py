from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd


def _bucket_from_mspd_class(security_class_1_description: str) -> str:
    t = (security_class_1_description or "").lower()
    if "bill" in t:
        return "SHORT"
    if "inflation" in t or "tips" in t:
        return "TIPS"
    if "note" in t or "bond" in t or "floating rate" in t or "frn" in t:
        return "NB"
    return "OTHER"


def find_latest_mspd_file(pattern: str = "input/MSPD_*.csv") -> Path:
    paths = sorted(Path().glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No files matched pattern: {pattern}")
    csvs = [p for p in paths if p.suffix.lower() == ".csv"]
    candidates = csvs if csvs else paths
    return max(candidates, key=lambda p: p.stat().st_mtime)


def build_outstanding_by_bucket_from_mspd(path: str | Path) -> pd.DataFrame:
    """
    Aggregate MSPD 'Detail of Marketable Treasury Securities Outstanding' rows to
    monthly outstanding stocks by marketable bucket in USD millions.

    Required columns (as in MSPD export):
      - Record Date
      - Security Type Description
      - Security Class 1 Description
      - Outstanding Amount (in Millions)

    Returns DataFrame with columns:
      - Record Date (month-end), stock_short, stock_nb, stock_tips
    """
    df = pd.read_csv(path)

    # Keep only marketable
    df = df[df["Security Type Description"].astype(str).str.lower() == "marketable"].copy()

    # Parse monthly dates and map to buckets
    df["Record Date"] = pd.to_datetime(df["Record Date"])  # month-end
    df["bucket"] = df["Security Class 1 Description"].astype(str).map(_bucket_from_mspd_class)

    value_col = "Outstanding Amount (in Millions)"
    if value_col not in df.columns:
        raise ValueError(f"Missing column: {value_col}")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce").fillna(0.0)

    grouped = (
        df[df["bucket"].isin(["SHORT", "NB", "TIPS"])]
        .groupby(["Record Date", "bucket"], as_index=False)[value_col]
        .sum()
        .pivot(index="Record Date", columns="bucket", values=value_col)
        .rename(columns={"SHORT": "stock_short", "NB": "stock_nb", "TIPS": "stock_tips"})
        .reset_index()
        .sort_values("Record Date")
    )

    for c in ["stock_short", "stock_nb", "stock_tips"]:
        if c not in grouped.columns:
            grouped[c] = 0.0

    return grouped[["Record Date", "stock_short", "stock_nb", "stock_tips"]]


def write_stocks_diagnostic(
    df: pd.DataFrame, out_path: str | Path = "output/diagnostics/outstanding_by_bucket.csv"
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out


