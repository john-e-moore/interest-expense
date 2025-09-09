from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import json
import pandas as pd

from macro.config import load_macro_yaml


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
    df = pd.read_csv(path, low_memory=False)

    # Keep only marketable and drop pre-aggregated totals
    df = df[df["Security Type Description"].astype(str).str.lower() == "marketable"].copy()
    df = df[~df["Security Class 1 Description"].astype(str).str.contains("total", case=False, na=False)].copy()
    # Also drop summary/total rows that appear in Class 2
    if "Security Class 2 Description" in df.columns:
        df = df[~df["Security Class 2 Description"].astype(str).str.contains("total", case=False, na=False)].copy()

    # Parse monthly dates and map to buckets
    df["Record Date"] = pd.to_datetime(df["Record Date"])  # month-end
    df["bucket"] = df["Security Class 1 Description"].astype(str).map(_bucket_from_mspd_class)

    # Use only 'Outstanding Amount (in Millions)' and drop nulls to avoid double counting
    col_out = "Outstanding Amount (in Millions)"
    if col_out not in df.columns:
        raise ValueError(f"Missing column: {col_out}")
    df[col_out] = pd.to_numeric(df[col_out], errors="coerce")
    df = df[df[col_out].notna()].copy()

    # Deduplicate per (Record Date, CUSIP) within each month to avoid within-month duplicates
    cusip_col = "Security Class 2 Description"
    if cusip_col in df.columns:
        df[cusip_col] = df[cusip_col].astype(str)
        df[cusip_col] = df[cusip_col].mask(df[cusip_col].str.lower().isin(["", "none", "nan", "null"]))
        df = (
            df[df[cusip_col].notna()]
            .sort_values(["Record Date", cusip_col, "Issue Date", "Maturity Date"], na_position="last")
            .drop_duplicates(subset=["Record Date", cusip_col], keep="last")
        )

    grouped = (
        df[df["bucket"].isin(["SHORT", "NB", "TIPS"])]
        .groupby(["Record Date", "bucket"], as_index=False)[col_out]
        .sum()
        .pivot(index="Record Date", columns="bucket", values=col_out)
        .rename(columns={"SHORT": "stock_short", "NB": "stock_nb", "TIPS": "stock_tips"})
        .fillna(0.0)
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


def build_mspd_processed_detail(path: str | Path) -> pd.DataFrame:
    """
    Return the processed MSPD detail rows (filtered/cleaned, bucket-mapped) without aggregation.
    Rows are marketable only, exclude 'Total*' classes, drop null outstanding, and include bucket.
    """
    df = pd.read_csv(path, low_memory=False)
    df = df[df["Security Type Description"].astype(str).str.lower() == "marketable"].copy()
    df = df[~df["Security Class 1 Description"].astype(str).str.contains("total", case=False, na=False)].copy()
    if "Security Class 2 Description" in df.columns:
        df = df[~df["Security Class 2 Description"].astype(str).str.contains("total", case=False, na=False)].copy()
    df["Record Date"] = pd.to_datetime(df["Record Date"])  # month-end
    df["bucket"] = df["Security Class 1 Description"].astype(str).map(_bucket_from_mspd_class)
    col_out = "Outstanding Amount (in Millions)"
    if col_out not in df.columns:
        raise ValueError(f"Missing column: {col_out}")
    df[col_out] = pd.to_numeric(df[col_out], errors="coerce")
    df = df[df[col_out].notna()].copy()

    # Deduplicate per (Record Date, CUSIP) within each month
    cusip_col = "Security Class 2 Description"
    if cusip_col in df.columns:
        df[cusip_col] = df[cusip_col].astype(str)
        df[cusip_col] = df[cusip_col].mask(df[cusip_col].str.lower().isin(["", "none", "nan", "null"]))
        df = (
            df[df[cusip_col].notna()]
            .sort_values(["Record Date", cusip_col, "Issue Date", "Maturity Date"], na_position="last")
            .drop_duplicates(subset=["Record Date", cusip_col], keep="last")
        )

    # Keep key identifier/context columns for inspection
    keep_cols = [
        "Record Date",
        "Security Class 1 Description",
        "Security Class 2 Description",
        "Issue Date",
        "Maturity Date",
        "bucket",
        col_out,
    ]
    existing = [c for c in keep_cols if c in df.columns]
    detail = df[existing].copy().sort_values("Record Date", ascending=False)
    return detail


def write_mspd_processed_detail(
    df: pd.DataFrame, out_path: str | Path = "output/diagnostics/mspd_processed_detail.csv"
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Ensure descending date order in output
    sort_col = "Record Date" if "Record Date" in df.columns else None
    if sort_col is not None:
        df = df.sort_values(sort_col, ascending=False)
    df.to_csv(out, index=False)
    return out


def _compute_target_rate_from_config(config_path: str | Path) -> Optional[float]:
    cfg = load_macro_yaml(config_path)
    if cfg.issuance_default_shares and cfg.rates_constant:
        s_short, s_nb, s_tips = cfg.issuance_default_shares
        r_short, r_nb, r_tips = cfg.rates_constant
        return s_short * r_short + s_nb * r_nb + s_tips * r_tips
    if cfg.rates_constant:
        r_short, r_nb, r_tips = cfg.rates_constant
        return (r_short + r_nb + r_tips) / 3.0
    return None


def scale_stocks_for_calibration(
    stocks_df: pd.DataFrame,
    fy_interest_df: pd.DataFrame,
    *,
    config_path: str | Path = "input/macro.yaml",
    r_target: Optional[float] = None,
    frame: str = "FY",
    year: Optional[int] = None,
) -> tuple[pd.DataFrame, float, float]:
    """
    Scale stocks uniformly so that implied effective rate ≈ r_target.

    Returns (scaled_df, factor, implied_rate_before).
    """
    if r_target is None:
        r_target = _compute_target_rate_from_config(config_path) or 0.03

    df = stocks_df.copy()
    df["Record Date"] = pd.to_datetime(df["Record Date"])  # ensure datetime
    df["total_stock"] = df[["stock_short", "stock_nb", "stock_tips"]].sum(axis=1)

    if frame.upper() == "FY":
        # Choose FY: prefer max FY present in interest table or infer from latest date
        fy_series = fy_interest_df.set_index("Fiscal Year")["Interest Expense"]
        fy_sel = int(fy_series.index.max() if year is None else year)
        I_target = float(fy_series.loc[fy_sel])
        fy_mask = df["Record Date"].dt.to_period("Y").dt.year.isin([fy_sel])
        stock_den = float(df.loc[fy_mask, "total_stock"].mean())
    else:
        I_target = float(fy_interest_df.set_index("Fiscal Year")["Interest Expense"].iloc[-1])
        latest_date = df["Record Date"].max()
        stock_den = float(df.loc[df["Record Date"] == latest_date, "total_stock"].iloc[0])

    implied_before = I_target / stock_den if stock_den else 0.0
    factor = I_target / (r_target * stock_den) if (r_target and stock_den) else 1.0

    for c in ("stock_short", "stock_nb", "stock_tips"):
        df[c] = df[c] * factor

    return df[["Record Date", "stock_short", "stock_nb", "stock_tips"]], factor, implied_before


def write_scaled_stocks_diagnostic(
    df_scaled: pd.DataFrame,
    factor: float,
    *,
    out_csv: str | Path = "output/diagnostics/outstanding_by_bucket_scaled.csv",
    out_json: str | Path = "output/diagnostics/stock_rescale_report.json",
    r_target: Optional[float] = None,
    implied_before: Optional[float] = None,
    implied_after: Optional[float] = None,
) -> tuple[Path, Path]:
    out_csv_p = Path(out_csv)
    out_csv_p.parent.mkdir(parents=True, exist_ok=True)
    df_scaled.to_csv(out_csv_p, index=False)

    report = {
        "factor": factor,
        "r_target": r_target,
        "implied_rate_before": implied_before,
        "implied_rate_after": implied_after,
    }
    out_json_p = Path(out_json)
    with out_json_p.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    return out_csv_p, out_json_p

