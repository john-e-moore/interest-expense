from __future__ import annotations

from pathlib import Path
from typing import Tuple

import matplotlib.pyplot as plt
import pandas as pd

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
    ax.plot(df["year"], df["interest"], marker="o", label="Interest")
    ax2 = ax.twinx()
    ax2.plot(df["year"], df["pct_gdp"], color="tab:red", marker="s", label="% of GDP")
    ax.set_title(title)
    ax.set_xlabel("Year")
    ax.set_ylabel("USD millions")
    ax2.set_ylabel("% of GDP")
    ax.grid(True, alpha=0.3)
    p = out_dir / ("annual_" + ("cy" if "calendar_year" in str(out_dir) else "fy") + ".png")
    fig.tight_layout()
    fig.savefig(p)
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
) -> Tuple[Path, Path, Path]:
    monthly = _read_monthly_trace(monthly_trace_path)
    # Plots
    p1 = _plot_monthly_interest(monthly, Path("output/calendar_year/visualizations"))
    p2 = _plot_effective_rate(monthly, Path("output/fiscal_year/visualizations"))
    _plot_annual(annual_cy_path, Path("output/calendar_year/visualizations"), "Annual CY Interest and %GDP")
    _plot_annual(annual_fy_path, Path("output/fiscal_year/visualizations"), "Annual FY Interest and %GDP")
    # Bridge
    bridge = build_bridge_table(monthly, macro_path)
    bridge_path = Path("output/diagnostics/bridge_table.csv")
    bridge_path.parent.mkdir(parents=True, exist_ok=True)
    bridge.to_csv(bridge_path, index=False)
    return p1, p2, bridge_path


