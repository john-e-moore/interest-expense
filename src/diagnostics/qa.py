from __future__ import annotations

from pathlib import Path
from typing import Tuple

import matplotlib.pyplot as plt
import pandas as pd
import json
from matplotlib.ticker import PercentFormatter

from core.dates import fiscal_year
from macro.config import load_macro_yaml
from macro.gdp import GDPModel


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
    # Compute monthly effective rate then aggregate to fiscal-year average (weighted by monthly stock)
    total_stock = df[["stock_short", "stock_nb", "stock_tips"]].sum(axis=1)
    monthly_rate = (df["interest_total"].astype(float) / total_stock.replace(0.0, pd.NA)).astype(float)
    # Weighted FY average: sum(interest) / avg(stock) per FY equals sum(monthly_rate * stock) / sum(stock)
    df_tmp = pd.DataFrame({
        "rate": monthly_rate,
        "stock": total_stock.astype(float),
    }, index=pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp())
    df_tmp["FY"] = df_tmp.index.map(fiscal_year)
    grouped = df_tmp.groupby("FY", as_index=True)
    # Avoid division by zero
    numer = (grouped.apply(lambda g: float((g["rate"] * g["stock"]).sum())))
    denom = (grouped.apply(lambda g: float(g["stock"].sum())))
    eff_fy = (numer / denom).astype(float) * 12.0
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(eff_fy.index.astype(int), eff_fy.values, label="Effective rate (FY annualized)")
    ax.set_title("Effective Interest Rate (FY annualized)")
    ax.set_xlabel("Fiscal Year")
    # Format as percentage with 1 decimal and remove y-axis title
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
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

    # Removed vertical cutoff line and label per updated design

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
    # Removed vertical cutoff line and label per updated design
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


def write_hist_forward_breakdown(
    monthly_df: pd.DataFrame,
    hist_path: str | Path,
    *,
    gdp_model: GDPModel,
    anchor_date: pd.Timestamp,
    frame: str,
    out_path: str | Path,
    hist_monthly_path: str | Path | None = None,
    stocks_path: str | Path | None = None,
) -> Path:
    """
    Write a spreadsheet with columns:
      year, gdp, interest_historical, interest_forward, interest_total,
      historical_pct_gdp, forward_pct_gdp, total_pct_gdp

    - frame: "FY" or "CY"
    - Uses the same splice logic as visuals: anchor year counts in forward.
    """
    if frame not in {"FY", "CY"}:
        raise ValueError("frame must be 'FY' or 'CY'")
    hist = pd.read_csv(hist_path)
    hist_series, fwd_series, _anchor_year = _compose_hist_vs_forward_series(
        monthly_df, hist, anchor_date=anchor_date, frame=frame
    )
    years = sorted(set(hist_series.index.tolist()) | set(fwd_series.index.tolist()))
    hist_vals = pd.Series({y: float(hist_series.get(y)) for y in years})
    fwd_vals = pd.Series({y: float(fwd_series.get(y)) for y in years})
    # Build GDP per frame
    def _safe_gdp_fy(y: int) -> float:
        try:
            return float(gdp_model.gdp_fy(int(y)))
        except Exception:  # noqa: BLE001
            return float("nan")
    def _safe_gdp_cy(y: int) -> float:
        try:
            return float(gdp_model.gdp_cy(int(y)))
        except Exception:  # noqa: BLE001
            return float("nan")
    if frame == "FY":
        gdp_map = {int(y): _safe_gdp_fy(int(y)) for y in years}
    else:
        gdp_map = {int(y): _safe_gdp_cy(int(y)) for y in years}

    out = pd.DataFrame(
        {
            "year": years,
            "gdp": [gdp_map[int(y)] for y in years],
            "interest_historical": [hist_vals.get(y) if pd.notna(hist_vals.get(y)) else float("nan") for y in years],
            "interest_forward": [fwd_vals.get(y) if pd.notna(fwd_vals.get(y)) else float("nan") for y in years],
        }
    )
    out["interest_total"] = out[["interest_historical", "interest_forward"]].fillna(0.0).sum(axis=1)
    out["historical_pct_gdp"] = out["interest_historical"] / out["gdp"]
    out["forward_pct_gdp"] = out["interest_forward"] / out["gdp"]
    out["total_pct_gdp"] = out["interest_total"] / out["gdp"]

    # Optional effective rates per bucket and average (annualized effective levels)
    if hist_monthly_path is not None and stocks_path is not None:
        # Prepare monthly bucket interest and stocks
        df = monthly_df.copy()
        df.index = pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp()
        fwd_bucket = df[["interest_short", "interest_nb", "interest_tips"]].astype(float)
        fwd_stocks = df[["stock_short", "stock_nb", "stock_tips"]].astype(float)
        hm = pd.read_csv(hist_monthly_path, parse_dates=["Record Date"]).sort_values("Record Date")
        hm["Record Date"] = hm["Record Date"].dt.to_period("M").dt.to_timestamp()
        keep = hm[hm["Debt Category"].isin(["SHORT", "NB", "TIPS"])].copy()
        hist_piv = keep.pivot_table(index="Record Date", columns="Debt Category", values="Interest Expense", aggfunc="sum").fillna(0.0)
        hist_piv = hist_piv.rename(columns={"SHORT": "interest_short", "NB": "interest_nb", "TIPS": "interest_tips"})
        s = pd.read_csv(stocks_path, parse_dates=["Record Date"]).sort_values("Record Date")
        s["Record Date"] = s["Record Date"].dt.to_period("M").dt.to_timestamp()
        s = s.set_index("Record Date")[ ["stock_short", "stock_nb", "stock_tips"] ]
        anchor = pd.Timestamp(anchor_date).to_period("M").to_timestamp()
        # Ensure coverage includes any months present in historical stocks as well
        months_all = sorted(
            set(hist_piv.index.tolist())
            | set(fwd_bucket.index.tolist())
            | set(s.index.tolist())
        )
        # Build combined interest and stocks per month (hist before anchor; fwd at/after)
        ib = pd.DataFrame(index=months_all)
        for c in ["interest_short", "interest_nb", "interest_tips"]:
            ib[c] = 0.0
            if not hist_piv.empty:
                ib.loc[ib.index < anchor, c] = hist_piv.reindex(ib.index).fillna(0.0)[c]
            ib.loc[ib.index >= anchor, c] = fwd_bucket.reindex(ib.index).fillna(0.0)[c]
        sb = pd.DataFrame(index=months_all)
        sb[["stock_short", "stock_nb", "stock_tips"]] = float("nan")
        if not s.empty:
            _idx_s = pd.Index(months_all).intersection(s.index)
            if len(_idx_s) > 0:
                sb.loc[_idx_s, ["stock_short", "stock_nb", "stock_tips"]] = s.loc[_idx_s, ["stock_short", "stock_nb", "stock_tips"]]
        _idx_f = pd.Index(months_all).intersection(fwd_stocks.index)
        if len(_idx_f) > 0:
            sb.loc[_idx_f, ["stock_short", "stock_nb", "stock_tips"]] = fwd_stocks.loc[_idx_f, ["stock_short", "stock_nb", "stock_tips"]]
        # Annualize effective rates by summing interest and dividing by average stock per year
        eff_short = []
        eff_nb = []
        eff_tips = []
        eff_avg = []
        for y in out["year"]:
            if frame == "FY":
                months = [d for d in months_all if fiscal_year(d) == int(y)]
            else:
                months = [d for d in months_all if pd.Timestamp(d).year == int(y)]
            if not months:
                eff_short.append(float("nan")); eff_nb.append(float("nan")); eff_tips.append(float("nan")); eff_avg.append(float("nan"))
                continue
            mb = ib.loc[months]
            sbm = sb.loc[months]
            rs = mb["interest_short"].sum() / (sbm["stock_short"].mean() or float("nan"))
            rn = mb["interest_nb"].sum() / (sbm["stock_nb"].mean() or float("nan"))
            rt = mb["interest_tips"].sum() / (sbm["stock_tips"].mean() or float("nan"))
            tot_i = mb[["interest_short", "interest_nb", "interest_tips"]].sum(axis=1).sum()
            tot_s = sbm[["stock_short", "stock_nb", "stock_tips"]].sum(axis=1).mean()
            ravg = tot_i / tot_s if pd.notna(tot_s) and tot_s not in (0.0,) else float("nan")
            eff_short.append(float(rs) if pd.notna(rs) else float("nan"))
            eff_nb.append(float(rn) if pd.notna(rn) else float("nan"))
            eff_tips.append(float(rt) if pd.notna(rt) else float("nan"))
            eff_avg.append(float(ravg) if pd.notna(ravg) else float("nan"))
        out["eff_rate_short"] = eff_short
        out["eff_rate_nb"] = eff_nb
        out["eff_rate_tips"] = eff_tips
        out["eff_rate_avg"] = eff_avg

    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(p, index=False)
    return p


def write_hist_forward_breakdown_monthly(
    monthly_df: pd.DataFrame,
    hist_monthly_path: str | Path,
    *,
    gdp_model: GDPModel,
    anchor_date: pd.Timestamp,
    frame: str,
    out_path: str | Path,
    stocks_path: str | Path | None = None,
) -> Path:
    """
    Monthly breakdown with columns:
      date, gdp, interest_historical, interest_forward, interest_total,
      historical_pct_gdp, forward_pct_gdp, total_pct_gdp

    Historical months are strictly before the anchor month; months at/after
    the anchor month are treated as forward.
    gdp is the annual level corresponding to the frame (FY or CY) of the row's date.
    """
    if frame not in {"FY", "CY"}:
        raise ValueError("frame must be 'FY' or 'CY'")
    # Normalize monthly_df index
    df = monthly_df.copy()
    df.index = pd.to_datetime(pd.DatetimeIndex(df.index)).to_period("M").to_timestamp()
    # Include other_interest if present
    total_col = "interest_total"
    if "other_interest" in df.columns:
        df["_total_interest"] = df["interest_total"].astype(float) + df["other_interest"].astype(float)
        total_col = "_total_interest"

    # Historical monthly totals (diagnostics file)
    hm = pd.read_csv(hist_monthly_path)
    # Expect 'Record Date' monthly and 'Interest Expense'
    if "Record Date" not in hm.columns or "Interest Expense" not in hm.columns:
        raise ValueError("historical monthly file missing expected columns")
    hm["Record Date"] = pd.to_datetime(hm["Record Date"]).dt.to_period("M").dt.to_timestamp()
    hist_m = hm.groupby("Record Date", as_index=True)["Interest Expense"].sum().astype(float)

    # Anchor month boundary
    anchor = pd.Timestamp(anchor_date).to_period("M").to_timestamp()

    # Build calendar of months to cover: union of hist (<anchor) and forward (>=anchor)
    months_hist = hist_m.index[hist_m.index < anchor]
    months_fwd = df.index[df.index >= anchor]
    all_months = pd.Index(sorted(set(months_hist.tolist()) | set(months_fwd.tolist())))

    # Compute per-month values
    hist_vals = pd.Series(0.0, index=all_months)
    fwd_vals = pd.Series(0.0, index=all_months)
    # Historical strictly before anchor
    hist_vals.loc[months_hist] = hist_m.reindex(months_hist).fillna(0.0).astype(float).values
    # Forward at/after anchor from projection
    fwd_vals.loc[months_fwd] = df.loc[months_fwd, total_col].astype(float).values

    # GDP mapping per frame
    def _safe_gdp_fy(y: int) -> float:
        try:
            return float(gdp_model.gdp_fy(int(y)))
        except Exception:  # noqa: BLE001
            return float("nan")
    def _safe_gdp_cy(y: int) -> float:
        try:
            return float(gdp_model.gdp_cy(int(y)))
        except Exception:  # noqa: BLE001
            return float("nan")
    if frame == "FY":
        gdp_vals = pd.Series({d: _safe_gdp_fy(int(fiscal_year(d))) for d in all_months})
    else:
        gdp_vals = pd.Series({d: _safe_gdp_cy(int(d.year)) for d in all_months})

    out = pd.DataFrame(
        {
            "date": all_months,
            "gdp": gdp_vals.values,
            "interest_historical": hist_vals.values,
            "interest_forward": fwd_vals.values,
        }
    )
    out["interest_total"] = out[["interest_historical", "interest_forward"]].sum(axis=1)
    out["historical_pct_gdp"] = out["interest_historical"] / out["gdp"]
    out["forward_pct_gdp"] = out["interest_forward"] / out["gdp"]
    out["total_pct_gdp"] = out["interest_total"] / out["gdp"]

    # Optional effective rates per bucket and average (monthly values)
    if stocks_path is not None:
        # Historical bucket interest
        hm2 = pd.read_csv(hist_monthly_path, parse_dates=["Record Date"]).sort_values("Record Date")
        hm2["Record Date"] = hm2["Record Date"].dt.to_period("M").dt.to_timestamp()
        piv_h = hm2.pivot_table(index="Record Date", columns="Debt Category", values="Interest Expense", aggfunc="sum").fillna(0.0)
        piv_h = piv_h.rename(columns={"SHORT": "interest_short", "NB": "interest_nb", "TIPS": "interest_tips"})
        # Forward bucket interest and stocks
        df2 = monthly_df.copy()
        df2.index = pd.to_datetime(pd.DatetimeIndex(df2.index)).to_period("M").to_timestamp()
        fwd_b = df2[["interest_short", "interest_nb", "interest_tips"]].astype(float)
        stocks_fwd = df2[["stock_short", "stock_nb", "stock_tips"]].astype(float)
        # Stocks hist
        s = pd.read_csv(stocks_path, parse_dates=["Record Date"]).sort_values("Record Date")
        s["Record Date"] = s["Record Date"].dt.to_period("M").dt.to_timestamp()
        s = s.set_index("Record Date")[ ["stock_short", "stock_nb", "stock_tips"] ]
        # Combine per month
        ishort = pd.Series(0.0, index=all_months)
        inb = pd.Series(0.0, index=all_months)
        itips = pd.Series(0.0, index=all_months)
        ishort.loc[all_months[all_months < anchor]] = piv_h.reindex(all_months).fillna(0.0)["interest_short"].loc[all_months[all_months < anchor]].values
        inb.loc[all_months[all_months < anchor]] = piv_h.reindex(all_months).fillna(0.0)["interest_nb"].loc[all_months[all_months < anchor]].values
        itips.loc[all_months[all_months < anchor]] = piv_h.reindex(all_months).fillna(0.0)["interest_tips"].loc[all_months[all_months < anchor]].values
        ishort.loc[all_months[all_months >= anchor]] = fwd_b.reindex(all_months).fillna(0.0)["interest_short"].loc[all_months[all_months >= anchor]].values
        inb.loc[all_months[all_months >= anchor]] = fwd_b.reindex(all_months).fillna(0.0)["interest_nb"].loc[all_months[all_months >= anchor]].values
        itips.loc[all_months[all_months >= anchor]] = fwd_b.reindex(all_months).fillna(0.0)["interest_tips"].loc[all_months[all_months >= anchor]].values
        sshort = pd.Series(float("nan"), index=all_months)
        snb = pd.Series(float("nan"), index=all_months)
        stips = pd.Series(float("nan"), index=all_months)
        _idx_hist = s.index.intersection(all_months)
        if len(_idx_hist) > 0:
            sshort.loc[_idx_hist] = s.loc[_idx_hist, "stock_short"]
            snb.loc[_idx_hist] = s.loc[_idx_hist, "stock_nb"]
            stips.loc[_idx_hist] = s.loc[_idx_hist, "stock_tips"]
        _idx_fwd = stocks_fwd.index.intersection(all_months)
        if len(_idx_fwd) > 0:
            sshort.loc[_idx_fwd] = stocks_fwd.loc[_idx_fwd, "stock_short"]
            snb.loc[_idx_fwd] = stocks_fwd.loc[_idx_fwd, "stock_nb"]
            stips.loc[_idx_fwd] = stocks_fwd.loc[_idx_fwd, "stock_tips"]
        out["eff_rate_short"] = (ishort / sshort).astype(float)
        out["eff_rate_nb"] = (inb / snb).astype(float)
        out["eff_rate_tips"] = (itips / stips).astype(float)
        out["eff_rate_avg"] = ((ishort + inb + itips) / (sshort + snb + stips)).astype(float)

    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(p, index=False)
    return p


def write_historical_shares(
    hist_monthly_path: str | Path,
    out_path: str | Path,
) -> Path:
    """
    Compute historical issuance shares by bucket from monthly interest by category.

    Output columns: date, share_short, share_nb, share_tips
    where shares are interest by bucket divided by sum over SHORT/NB/TIPS for that month.
    """
    df = pd.read_csv(hist_monthly_path, parse_dates=["Record Date"]).sort_values("Record Date")
    keep = df[df["Debt Category"].isin(["SHORT", "NB", "TIPS"])].copy()
    keep["Record Date"] = keep["Record Date"].dt.to_period("M").dt.to_timestamp()
    piv = keep.pivot_table(
        index="Record Date", columns="Debt Category", values="Interest Expense", aggfunc="sum"
    ).fillna(0.0)
    piv = piv.rename(columns={"SHORT": "short", "NB": "nb", "TIPS": "tips"})
    total = piv[["short", "nb", "tips"]].sum(axis=1).replace(0.0, pd.NA)
    shares = pd.DataFrame(index=piv.index)
    shares["share_short"] = (piv["short"] / total).astype(float)
    shares["share_nb"] = (piv["nb"] / total).astype(float)
    shares["share_tips"] = (piv["tips"] / total).astype(float)
    shares = shares.reset_index().rename(columns={"Record Date": "date"})
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    shares.to_csv(p, index=False)
    return p


def write_historical_effective_rates(
    hist_monthly_path: str | Path,
    stocks_path: str | Path,
    out_path: str | Path,
) -> Path:
    """
    Compute historical effective rates by bucket using historical interest and stocks:
    rate_bucket_m = interest_bucket_month / stock_bucket_month; also annualized = *12.

    Output columns:
      date, rate_short_m, rate_nb_m, rate_tips_m, rate_total_m,
      rate_short_a, rate_nb_a, rate_tips_a, rate_total_a
    """
    # Interest by category
    df = pd.read_csv(hist_monthly_path, parse_dates=["Record Date"]).sort_values("Record Date")
    keep = df[df["Debt Category"].isin(["SHORT", "NB", "TIPS"])].copy()
    keep["Record Date"] = keep["Record Date"].dt.to_period("M").dt.to_timestamp()
    piv = keep.pivot_table(
        index="Record Date", columns="Debt Category", values="Interest Expense", aggfunc="sum"
    ).fillna(0.0)
    piv = piv.rename(columns={"SHORT": "interest_short", "NB": "interest_nb", "TIPS": "interest_tips"})

    # Stocks by bucket (scaled)
    s = pd.read_csv(stocks_path, parse_dates=["Record Date"]).sort_values("Record Date")
    s["Record Date"] = s["Record Date"].dt.to_period("M").dt.to_timestamp()
    s = s.set_index("Record Date")[ ["stock_short", "stock_nb", "stock_tips"] ]

    merged = piv.join(s, how="inner")
    # Effective monthly rates
    rate_short_m = (merged["interest_short"] / merged["stock_short"]).astype(float)
    rate_nb_m = (merged["interest_nb"] / merged["stock_nb"]).astype(float)
    rate_tips_m = (merged["interest_tips"] / merged["stock_tips"]).astype(float)
    total_interest = merged[["interest_short", "interest_nb", "interest_tips"]].sum(axis=1)
    total_stock = merged[["stock_short", "stock_nb", "stock_tips"]].sum(axis=1).replace(0.0, pd.NA)
    rate_total_m = (total_interest / total_stock).astype(float)

    out = pd.DataFrame(
        {
            "date": merged.index,
            "rate_short_m": rate_short_m.values,
            "rate_nb_m": rate_nb_m.values,
            "rate_tips_m": rate_tips_m.values,
            "rate_total_m": rate_total_m.values,
        }
    )
    for col in ["rate_short_m", "rate_nb_m", "rate_tips_m", "rate_total_m"]:
        out[col.replace("_m", "_a")] = out[col] * 12.0
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(p, index=False)
    return p


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


