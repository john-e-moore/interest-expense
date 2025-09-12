from __future__ import annotations

from pathlib import Path
from typing import Tuple

import matplotlib.pyplot as plt
import pandas as pd
import json
from matplotlib.ticker import PercentFormatter

from core.dates import fiscal_year
from macro.config import load_macro_yaml


def _read_monthly_trace(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".parquet" and p.exists():
        try:
            df = pd.read_parquet(p)
        except Exception:
            df = pd.read_csv(p.with_suffix(".csv"))
    else:
        # default to CSV
        if p.exists():
            df = pd.read_csv(p)
        elif p.with_suffix(".csv").exists():
            df = pd.read_csv(p.with_suffix(".csv"))
        else:
            raise FileNotFoundError(f"Monthly trace not found: {p}")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
        df = df.set_index("date")
    else:
        df.index = pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp()
        df.index.name = "date"
    return df


def _plot_monthly_interest(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(df.index, df["interest_total"], label="Interest (marketable)")
    if "other_interest" in df.columns:
        ax.plot(df.index, df["interest_total"] + df["other_interest"], label="Interest (total)")
    ax.set_title("Monthly Interest")
    ax.set_ylabel("USD millions")
    ax.legend()
    ax.grid(True, alpha=0.3)
    p = out_dir / "monthly_interest.png"
    fig.tight_layout()
    fig.savefig(p)
    plt.close(fig)
    return p


def _plot_effective_rate(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    total_stock = df[["stock_short", "stock_nb", "stock_tips"]].sum(axis=1)
    eff = (df["interest_total"].astype(float) / total_stock.replace(0.0, pd.NA)).astype(float)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(df.index, eff, label="Effective rate (monthly interest / avg stock)")
    ax.set_title("Effective Interest Rate (Approx)")
    ax.set_ylabel("per month (approx)")
    ax.grid(True, alpha=0.3)
    p = out_dir / "effective_rate.png"
    fig.tight_layout()
    fig.savefig(p)
    plt.close(fig)
    return p


def _plot_annual(annual_path: str | Path, out_dir: Path, title: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(annual_path)
    fig, ax = plt.subplots(figsize=(9, 4))
    # Left axis: % of GDP with 1-decimal percent formatter
    ax.plot(df["year"], df["pct_gdp"], color="tab:red", marker="s", label="% of GDP")
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    ax.set_ylabel("% of GDP")
    # Right axis: USD trillions (interest is in USD millions in CSV)
    ax2 = ax.twinx()
    interest_trn = (df["interest"].astype(float) / 1_000_000.0)
    ax2.plot(df["year"], interest_trn, marker="o", label="Interest")
    ax2.set_ylabel("USD trillions")
    ax.set_title(title)
    ax.set_xlabel("Year")
    ax.grid(True, alpha=0.3)
    p = out_dir / ("annual_" + ("cy" if "calendar_year" in str(out_dir) else "fy") + ".png")
    fig.tight_layout()
    fig.savefig(p)
    # Write minimal metadata for verification in tests
    meta = {
        "right_ylabel": ax2.get_ylabel(),
        "left_ticklabels": [t.get_text() for t in ax.get_yticklabels()],
    }
    p.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    plt.close(fig)
    return p


def _compose_hist_vs_forward_series(
    monthly_df: pd.DataFrame,
    hist_df: pd.DataFrame,
    *,
    anchor_date: pd.Timestamp,
    frame: str = "FY",
) -> Tuple[pd.Series, pd.Series, int]:
    """
    Build two annual series split at the anchor year: historical and forward.

    - historical_series: totals strictly before anchor year + anchor-year historical YTD
    - forward_series: anchor-year forward remainder + totals strictly after anchor year

    frame: "FY" or "CY". hist_df must have columns:
      FY → ["Fiscal Year", "Interest Expense"], CY → ["Calendar Year", "Interest Expense"].
    Returns (historical_series, forward_series, anchor_year)
    """
    if frame not in {"FY", "CY"}:
        raise ValueError("frame must be 'FY' or 'CY'")

    df = monthly_df.copy()
    df.index = pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp()
    # Include other_interest if present to match historical coverage
    total_col = "interest_total"
    if "other_interest" in df.columns:
        df["_total_interest"] = df["interest_total"].astype(float) + df["other_interest"].astype(float)
        total_col = "_total_interest"

    if frame == "FY":
        df["Y"] = df.index.map(fiscal_year)
        year_col = "Fiscal Year"
    else:
        df["Y"] = df.index.year
        year_col = "Calendar Year"

    # Determine anchor month start
    anchor = pd.Timestamp(anchor_date).to_period("M").to_timestamp()
    # Forward remainder: only months at/after anchor
    fwd_remainder = df.loc[df.index >= anchor].groupby("Y", as_index=True)[total_col].sum()

    # Historical totals (up to anchor date) – assume provided file is YTD for anchor year
    if year_col not in hist_df.columns or "Interest Expense" not in hist_df.columns:
        raise ValueError("historical totals missing expected columns")
    hist_tbl = (
        hist_df[[year_col, "Interest Expense"]]
        .dropna()
        .rename(columns={year_col: "Y", "Interest Expense": "hist"})
        .set_index("Y")["hist"]
        .astype(float)
    )

    anchor_year = int(anchor.year if frame == "CY" else fiscal_year(anchor))

    # Build aligned year index covering both
    years = sorted(set(hist_tbl.index.tolist()) | set(fwd_remainder.index.tolist()))
    # Historical part (T4b): years < anchor_year use full historical; anchor_year excluded
    hist_series = pd.Series(index=years, dtype=float)
    for y in years:
        if y < anchor_year:
            hist_series.loc[y] = float(hist_tbl.get(y, float("nan")))
        elif y == anchor_year:
            # Exclude current year from historical (plot as forward)
            hist_series.loc[y] = float("nan")
        else:
            hist_series.loc[y] = float("nan")

    # Forward part (T4b): anchor year = historical YTD + forward remainder; years after = forward totals
    fwd_series = pd.Series(index=years, dtype=float)
    for y in years:
        if y < anchor_year:
            fwd_series.loc[y] = float("nan")
        elif y == anchor_year:
            fwd_series.loc[y] = float(fwd_remainder.get(y, 0.0)) + float(hist_tbl.get(y, 0.0))
        else:
            fwd_series.loc[y] = float(fwd_remainder.get(y, float("nan")))

    return hist_series, fwd_series, anchor_year


def _plot_historical_vs_forward(
    monthly_df: pd.DataFrame,
    hist_fy_path: str | Path,
    *,
    macro_path: str | Path,
    out_dir: Path,
    frame: str,
) -> Path:
    """
    Create an overlay chart of historical vs forward annual interest (FY),
    splicing anchor-year as historical YTD + forward remainder.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_macro_yaml(macro_path)
    hist_fy = pd.read_csv(hist_fy_path)
    hist_series, fwd_series, anchor_year = _compose_hist_vs_forward_series(
        monthly_df, hist_fy, anchor_date=cfg.anchor_date, frame=frame
    )

    # Plot
    fig, ax = plt.subplots(figsize=(9, 4))
    # Convert from USD millions to USD trillions for readability
    scale = 1_000_000.0
    ax.plot(hist_series.index, (hist_series.values / scale), label="Historical", color="tab:blue", marker="o")
    ax.plot(fwd_series.index, (fwd_series.values / scale), label="Forward", color="tab:orange", marker="s")
    if frame == "FY":
        ax.set_title("Historical vs Forward Interest (FY)")
        ax.set_xlabel("Fiscal Year")
    else:
        ax.set_title("Historical vs Forward Interest (CY)")
        ax.set_xlabel("Calendar Year")
    ax.set_ylabel("USD trillions")
    ax.grid(True, alpha=0.3)
    ax.legend()

    # Vertical cutoff at anchor year between hist and fwd
    ax.axvline(anchor_year + 0.0, color="k", linestyle="--", alpha=0.6)
    ax.annotate(
        "forecast starts",
        xy=(anchor_year + 0.02, ax.get_ylim()[1] * 0.9),
        fontsize=9,
        color="k",
    )

    p = out_dir / "historical_vs_forward.png"
    fig.tight_layout()
    fig.savefig(p)
    # Minimal metadata to assist tests
    meta = {
        "legend": [t.get_text() for t in ax.get_legend().get_texts()],
        "anchor_year": int(anchor_year),
    }
    p.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    plt.close(fig)
    return p


def _plot_historical_vs_forward_pct_gdp(
    monthly_df: pd.DataFrame,
    hist_path: str | Path,
    *,
    macro_path: str | Path,
    out_dir: Path,
    frame: str,
) -> Path:
    """
    Plot historical vs forward as % of GDP for FY or CY.
    """
    from macro.gdp import build_gdp_function

    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_macro_yaml(macro_path)
    hist = pd.read_csv(hist_path)
    hist_series, fwd_series, anchor_year = _compose_hist_vs_forward_series(
        monthly_df, hist, anchor_date=cfg.anchor_date, frame=frame
    )
    # Build GDP model using FY growth from config when available; otherwise flat
    years = list(hist_series.index)
    if years:
        min_year = int(min(years))
        max_year = int(max(years))
    else:
        min_year = int(cfg.gdp_anchor_fy)
        max_year = int(cfg.gdp_anchor_fy)

    if getattr(cfg, "gdp_annual_fy_growth_rate", None):
        # Config growth is percent; convert to decimals and fill coverage for [min_year, max_year+1]
        provided = {int(y): float(v) / 100.0 for y, v in cfg.gdp_annual_fy_growth_rate.items()}
        years_needed = list(range(min_year, max_year + 2))
        # Forward-fill from earliest provided for years below; then step through years needed
        if provided:
            sorted_keys = sorted(provided)
            current = provided.get(sorted_keys[0], 0.0)
        else:
            current = 0.0
        growth_fy = {}
        for y in years_needed:
            if y in provided:
                current = provided[y]
            growth_fy[y] = current
    else:
        # Flat growth across coverage
        growth_fy = {int(y): 0.0 for y in range(min_year, max_year + 2)}

    gdp_model = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, growth_fy)
    if frame == "FY":
        denom = hist_series.index.map(gdp_model.gdp_fy)
        title = "Historical vs Forward Interest (%GDP, FY)"
        xlabel = "Fiscal Year"
    else:
        denom = hist_series.index.map(gdp_model.gdp_cy)
        title = "Historical vs Forward Interest (%GDP, CY)"
        xlabel = "Calendar Year"

    hist_pct = hist_series / denom
    fwd_pct = fwd_series / denom

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(hist_pct.index, hist_pct.values, label="Historical", color="tab:blue", marker="o")
    ax.plot(fwd_pct.index, fwd_pct.values, label="Forward", color="tab:orange", marker="s")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("% of GDP")
    # Format with 1-decimal percent ticks to match annual charts
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.axvline(anchor_year + 0.0, color="k", linestyle="--", alpha=0.6)
    ax.annotate("forecast starts", xy=(anchor_year + 0.02, ax.get_ylim()[1] * 0.9), fontsize=9, color="k")
    p = out_dir / ("historical_vs_forward_pct_gdp.png")
    fig.tight_layout()
    fig.savefig(p)
    # Write simple metadata to aid tests
    meta = {
        "left_ticklabels": [t.get_text() for t in ax.get_yticklabels()],
        "frame": frame,
    }
    p.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    plt.close(fig)
    return p


def build_bridge_table(monthly_df: pd.DataFrame, macro_path: str | Path) -> pd.DataFrame:
    cfg = load_macro_yaml(macro_path)
    anchor_fy = cfg.gdp_anchor_fy
    def _fy_sum(col: str, fy: int) -> float:
        mask = monthly_df.index.map(fiscal_year) == fy
        return float(monthly_df.loc[mask, col].sum())
    def _fy_avg_stock(fy: int) -> float:
        mask = monthly_df.index.map(fiscal_year) == fy
        return float(monthly_df.loc[mask, ["stock_short", "stock_nb", "stock_tips"]].sum(axis=1).mean())

    fy0, fy1 = anchor_fy, anchor_fy + 1
    int0 = _fy_sum("interest_total", fy0)
    int1 = _fy_sum("interest_total", fy1)
    oth0 = _fy_sum("other_interest", fy0) if "other_interest" in monthly_df.columns else 0.0
    oth1 = _fy_sum("other_interest", fy1) if "other_interest" in monthly_df.columns else 0.0
    delta_total = (int1 + oth1) - (int0 + oth0)

    avgS0 = _fy_avg_stock(fy0) or 1.0
    avgS1 = _fy_avg_stock(fy1) or 1.0
    base0 = int0
    base1 = int1
    r0 = base0 / avgS0
    r1 = base1 / avgS1

    other_effect = oth1 - oth0
    delta_base = delta_total - other_effect

    stock_effect = (avgS1 - avgS0) * r0
    rate_effect = avgS0 * (r1 - r0)
    mix_effect = delta_base - stock_effect - rate_effect
    tips_accretion = 0.0

    bridge = pd.DataFrame(
        [
            {
                "fy_from": fy0,
                "fy_to": fy1,
                "delta_interest": delta_total,
                "stock_effect": stock_effect,
                "rate_effect": rate_effect,
                "mix_term_effect": mix_effect,
                "tips_accretion": tips_accretion,
                "other_effect": other_effect,
            }
        ]
    )
    return bridge


def run_qa(
    monthly_trace_path: str | Path = "output/diagnostics/monthly_trace.parquet",
    annual_cy_path: str | Path = "output/calendar_year/spreadsheets/annual.csv",
    annual_fy_path: str | Path = "output/fiscal_year/spreadsheets/annual.csv",
    macro_path: str | Path = "input/macro.yaml",
    out_base: str | Path | None = None,
) -> Tuple[Path, Path, Path]:
    monthly = _read_monthly_trace(monthly_trace_path)
    # Plots (route to out_base if provided)
    base = Path(out_base) if out_base is not None else Path("output")
    cy_vis_dir = base / "calendar_year" / "visualizations"
    fy_vis_dir = base / "fiscal_year" / "visualizations"
    # FY/CY and pctGDP variants
    p1 = _plot_monthly_interest(monthly, cy_vis_dir)
    p2 = _plot_effective_rate(monthly, fy_vis_dir)
    _plot_annual(annual_cy_path, cy_vis_dir, "Annual CY Interest and %GDP")
    _plot_annual(annual_fy_path, fy_vis_dir, "Annual FY Interest and %GDP")
    # Historical vs Forward overlays
    _plot_historical_vs_forward(
        monthly,
        hist_fy_path=base / "diagnostics" / "interest_fy_totals.csv",
        macro_path=macro_path,
        out_dir=fy_vis_dir,
        frame="FY",
    )
    _plot_historical_vs_forward(
        monthly,
        hist_fy_path=base / "diagnostics" / "interest_cy_totals.csv",
        macro_path=macro_path,
        out_dir=cy_vis_dir,
        frame="CY",
    )
    _plot_historical_vs_forward_pct_gdp(
        monthly,
        hist_path=base / "diagnostics" / "interest_fy_totals.csv",
        macro_path=macro_path,
        out_dir=fy_vis_dir,
        frame="FY",
    )
    _plot_historical_vs_forward_pct_gdp(
        monthly,
        hist_path=base / "diagnostics" / "interest_cy_totals.csv",
        macro_path=macro_path,
        out_dir=cy_vis_dir,
        frame="CY",
    )
    # Bridge
    bridge = build_bridge_table(monthly, macro_path)
    bridge_path = (base / "diagnostics" / "bridge_table.csv")
    bridge_path.parent.mkdir(parents=True, exist_ok=True)
    bridge.to_csv(bridge_path, index=False)
    return p1, p2, bridge_path


