from __future__ import annotations

from pathlib import Path

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
    df = pd.read_csv(path, low_memory=False)

    # Keep only marketable and drop pre-aggregated totals
    df = df[df["Security Type Description"].astype(str).str.lower() == "marketable"].copy()
    df = df[~df["Security Class 1 Description"].astype(str).str.contains("total", case=False, na=False)].copy()

    # Parse monthly dates and map to buckets
    df["Record Date"] = pd.to_datetime(df["Record Date"])  # month-end
    df["bucket"] = df["Security Class 1 Description"].astype(str).map(_bucket_from_mspd_class)

    # Use only 'Outstanding Amount (in Millions)' and drop nulls to avoid double counting
    col_out = "Outstanding Amount (in Millions)"
    if col_out not in df.columns:
        raise ValueError(f"Missing column: {col_out}")
    df[col_out] = pd.to_numeric(df[col_out], errors="coerce")
    df = df[df[col_out].notna()].copy()

    # Deduplicate by (Record Date, CUSIP) keeping the most recent (by Issue Date, then Maturity Date)
    cusip_col = "Security Class 2 Description"
    if cusip_col in df.columns:
        df[cusip_col] = df[cusip_col].astype(str)
        # Treat placeholder strings as missing
        df[cusip_col] = df[cusip_col].mask(df[cusip_col].str.lower().isin(["", "none", "nan", "null"]))
        df["Issue Date"] = pd.to_datetime(df.get("Issue Date"), errors="coerce")
        df["Maturity Date"] = pd.to_datetime(df.get("Maturity Date"), errors="coerce")
        with_cusip = df[df[cusip_col].notna()].copy()
        without_cusip = df[df[cusip_col].isna()].copy()
        with_cusip = with_cusip.sort_values(["Record Date", cusip_col, "Issue Date", "Maturity Date"]).drop_duplicates(
            subset=["Record Date", cusip_col], keep="last"
        )
        df = pd.concat([with_cusip, without_cusip], ignore_index=True)

    # Keep only the most recent month overall per CUSIP to avoid double counting across months
    cusip_col = "Security Class 2 Description"
    if cusip_col in df.columns:
        df[cusip_col] = df[cusip_col].astype(str)
        df[cusip_col] = df[cusip_col].mask(df[cusip_col].str.lower().isin(["", "none", "nan", "null"]))
        df = (
            df[df[cusip_col].notna()]
            .sort_values([cusip_col, "Record Date"])  # ascending date, keep last later
            .drop_duplicates(subset=[cusip_col], keep="last")
        )

    grouped = (
        df[df["bucket"].isin(["SHORT", "NB", "TIPS"])]
        .groupby(["Record Date", "bucket"], as_index=False)[col_out]
        .sum()
        .pivot(index="Record Date", columns="bucket", values=col_out)
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


def build_mspd_processed_detail(path: str | Path) -> pd.DataFrame:
    """
    Return the processed MSPD detail rows (filtered/cleaned, bucket-mapped) without aggregation.
    Rows are marketable only, exclude 'Total*' classes, drop null outstanding, and include bucket.
    """
    df = pd.read_csv(path, low_memory=False)
    df = df[df["Security Type Description"].astype(str).str.lower() == "marketable"].copy()
    df = df[~df["Security Class 1 Description"].astype(str).str.contains("total", case=False, na=False)].copy()
    df["Record Date"] = pd.to_datetime(df["Record Date"])  # month-end
    df["bucket"] = df["Security Class 1 Description"].astype(str).map(_bucket_from_mspd_class)
    col_out = "Outstanding Amount (in Millions)"
    if col_out not in df.columns:
        raise ValueError(f"Missing column: {col_out}")
    df[col_out] = pd.to_numeric(df[col_out], errors="coerce")
    df = df[df[col_out].notna()].copy()

    # Keep only the most recent month overall per CUSIP
    cusip_col = "Security Class 2 Description"
    if cusip_col in df.columns:
        df[cusip_col] = df[cusip_col].astype(str)
        df[cusip_col] = df[cusip_col].mask(df[cusip_col].str.lower().isin(["", "none", "nan", "null"]))
        df = (
            df[df[cusip_col].notna()]
            .sort_values([cusip_col, "Record Date"])  # ascending date
            .drop_duplicates(subset=[cusip_col], keep="last")
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

