from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, Optional
import logging

import pandas as pd

from core.dates import fiscal_year
from macro.config import MacroConfig
from macro.gdp import GDPModel


def _fill_year_map(values: Dict[int, float], years_needed: list[int]) -> Dict[int, float]:
    if not values:
        return {y: 0.0 for y in years_needed}
    filled: Dict[int, float] = {}
    sorted_years = sorted(set([*years_needed, *values.keys()]))
    current = values.get(min(values.keys()), 0.0)
    for y in sorted_years:
        if y in values:
            current = float(values[y])
        filled[y] = current
    return {y: filled[y] for y in years_needed}


def build_budget_component_series(
    cfg: MacroConfig,
    gdp_model: GDPModel,
    index: pd.DatetimeIndex,
) -> Tuple[pd.Series, pd.Series, pd.DataFrame]:
    """
    Build monthly revenue and primary outlays series (USD millions per month) from
    annual % of GDP maps under the budget frame (FY or CY).

    Returns (revenue_month, outlays_month, preview_df)
    preview columns: date, frame, year_key, revenue_pct_gdp, outlays_pct_gdp,
                     gdp, revenue_annual_usd_mn, outlays_annual_usd_mn,
                     revenue_month_usd_mn, outlays_month_usd_mn
    """
    idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()

    # Determine coverage years needed for frame
    if cfg.deficits_frame == "FY":
        years_needed = sorted(set([fiscal_year(d) for d in idx]))
        get_gdp = lambda y: float(gdp_model.gdp_fy(int(y)))
        year_of = lambda d: fiscal_year(d)
    else:
        years_needed = sorted(set([d.year for d in idx]))
        get_gdp = lambda y: float(gdp_model.gdp_cy(int(y)))
        year_of = lambda d: int(pd.Timestamp(d).year)

    rev_map = {int(k): float(v) for k, v in (getattr(cfg, "budget_annual_revenue_pct_gdp", {}) or {}).items()}
    out_map = {int(k): float(v) for k, v in (getattr(cfg, "budget_annual_outlays_pct_gdp", {}) or {}).items()}
    rev_filled = _fill_year_map(rev_map, years_needed)
    out_filled = _fill_year_map(out_map, years_needed)

    rows = []
    rev_vals = []
    out_vals = []
    for d in idx:
        y = year_of(d)
        gdp = get_gdp(y)
        r_pct = float(rev_filled.get(int(y), 0.0))
        o_pct = float(out_filled.get(int(y), 0.0))
        r_ann = (r_pct / 100.0) * gdp
        o_ann = (o_pct / 100.0) * gdp
        r_m = r_ann / 12.0
        o_m = o_ann / 12.0
        rev_vals.append(r_m)
        out_vals.append(o_m)
        rows.append(
            {
                "date": d,
                "frame": cfg.deficits_frame,
                "year_key": int(y),
                "revenue_pct_gdp": r_pct,
                "primary_outlays_pct_gdp": o_pct,
                "gdp": gdp,
                "revenue_annual_usd_mn": r_ann,
                "primary_outlays_annual_usd_mn": o_ann,
                "revenue_month_usd_mn": r_m,
                "primary_outlays_month_usd_mn": o_m,
            }
        )

    revenue_series = pd.Series(rev_vals, index=idx, name="revenue")
    outlays_series = pd.Series(out_vals, index=idx, name="primary_outlays")
    preview = pd.DataFrame(rows)
    return revenue_series, outlays_series, preview


def build_deficits_preview_monthly(
    cfg: MacroConfig,
    gdp_model: GDPModel,
    index: pd.DatetimeIndex,
    revenue_series: pd.Series,
    outlays_series: pd.Series,
    additional_series: Optional[pd.Series] = None,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Compose the expanded monthly deficits preview and return it along with
    base and adjusted primary deficit series.
    """
    idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()
    base = (outlays_series.reindex(idx).fillna(0.0) - revenue_series.reindex(idx).fillna(0.0)).rename("primary_deficit_base")
    if additional_series is not None:
        adj = (base - additional_series.reindex(idx).fillna(0.0)).rename("primary_deficit_adj")
    else:
        adj = base.copy().rename("primary_deficit_adj")

    # Build per-month rows by recomputing the annual values on the fly for clarity
    rows = []
    if cfg.deficits_frame == "FY":
        year_of = lambda d: fiscal_year(d)
        get_gdp = lambda y: float(gdp_model.gdp_fy(int(y)))
    else:
        year_of = lambda d: int(pd.Timestamp(d).year)
        get_gdp = lambda y: float(gdp_model.gdp_cy(int(y)))

    mode = getattr(cfg, "additional_revenue_mode", None)
    for d in idx:
        y = year_of(d)
        gdp = get_gdp(y)
        r_m = float(revenue_series.get(d, 0.0))
        o_m = float(outlays_series.get(d, 0.0))
        add_m = float(additional_series.get(d, 0.0)) if additional_series is not None else 0.0
        # Annualize (flat by month in year) and shares
        r_ann = r_m * 12.0
        o_ann = o_m * 12.0
        base_m = float(base.get(d, 0.0))
        base_ann = base_m * 12.0
        adj_m = float(adj.get(d, 0.0))
        adj_ann = adj_m * 12.0
        rows.append(
            {
                "date": d,
                "frame": cfg.deficits_frame,
                "year_key": int(y),
                "gdp": gdp,
                "revenue_pct_gdp": (r_ann / gdp) * 100.0 if gdp else 0.0,
                "revenue_annual_usd_mn": r_ann,
                "revenue_month_usd_mn": r_m,
                "primary_outlays_pct_gdp": (o_ann / gdp) * 100.0 if gdp else 0.0,
                "primary_outlays_annual_usd_mn": o_ann,
                "primary_outlays_month_usd_mn": o_m,
                "additional_revenue_mode": mode if mode else "",
                "additional_revenue_input_value": float("nan"),  # unknown at monthly level when using anchor/index
                "additional_revenue_annual_usd_mn": add_m * 12.0,
                "additional_revenue_month_usd_mn": add_m,
                "primary_deficit_base_pct_gdp": (base_ann / gdp) * 100.0 if gdp else 0.0,
                "primary_deficit_base_annual_usd_mn": base_ann,
                "primary_deficit_base_month_usd_mn": base_m,
                "primary_deficit_adj_pct_gdp": (adj_ann / gdp) * 100.0 if gdp else 0.0,
                "primary_deficit_adj_annual_usd_mn": adj_ann,
                "primary_deficit_adj_month_usd_mn": adj_m,
            }
        )

    preview = pd.DataFrame(rows)

    # Sanity checks & guardrails (warn-level)
    try:
        logger = logging.getLogger("run")
        # Range checks on annual shares per year
        if not preview.empty:
            annual_shares = (
                preview.groupby(["frame", "year_key"], as_index=False)[
                    [
                        "revenue_pct_gdp",
                        "primary_outlays_pct_gdp",
                        "primary_deficit_adj_pct_gdp",
                    ]
                ].first()
            )
            for _, row in annual_shares.iterrows():
                y = int(row["year_key"])
                rv = float(row["revenue_pct_gdp"])
                ou = float(row["primary_outlays_pct_gdp"])
                da = float(row["primary_deficit_adj_pct_gdp"])
                if not (10.0 <= rv <= 25.0):
                    logger.warning("REVENUE_SHARE_RANGE frame=%s year=%d value=%.3f%%", cfg.deficits_frame, y, rv)
                if not (15.0 <= ou <= 30.0):
                    logger.warning("OUTLAYS_SHARE_RANGE frame=%s year=%s value=%.3f%%", cfg.deficits_frame, y, ou)
                if abs(da) > 10.0:
                    logger.warning("DEFICIT_SHARE_MAG frame=%s year=%s value=%.3f%%", cfg.deficits_frame, y, da)

            # Identity checks using monthly sums per year
            pm = preview.copy()
            # Monthly sums per year
            sums = pm.groupby(["frame", "year_key"], as_index=False)[
                [
                    "revenue_month_usd_mn",
                    "primary_outlays_month_usd_mn",
                    "additional_revenue_month_usd_mn",
                    "primary_deficit_base_month_usd_mn",
                    "primary_deficit_adj_month_usd_mn",
                ]
            ].sum()
            # Month counts per year (FY/CY aware)
            counts = pm.groupby(["frame", "year_key"], as_index=False).size().rename(columns={"size": "months"})
            sums = sums.merge(counts, on=["frame", "year_key"], how="left")
            for _, row in sums.iterrows():
                y = int(row["year_key"])
                months = int(row["months"])
                rev_sum = float(row["revenue_month_usd_mn"])  # noqa: N806
                out_sum = float(row["primary_outlays_month_usd_mn"])  # noqa: N806
                add_sum = float(row["additional_revenue_month_usd_mn"])  # noqa: N806
                base_sum = float(row["primary_deficit_base_month_usd_mn"])  # noqa: N806
                adj_sum = float(row["primary_deficit_adj_month_usd_mn"])  # noqa: N806
                tol_abs = 0.5  # USD mn
                tol_rel = 1e-6
                # Identities
                if months >= 12:
                    if abs((out_sum - rev_sum) - base_sum) > max(tol_abs, tol_rel * max(1.0, abs(base_sum))):
                        logger.warning(
                            "IDENTITY_MISMATCH_BASE frame=%s year=%d outlays-revenue=%.3f base=%.3f",
                            cfg.deficits_frame,
                            y,
                            out_sum - rev_sum,
                            base_sum,
                        )
                    if abs((base_sum - add_sum) - adj_sum) > max(tol_abs, tol_rel * max(1.0, abs(adj_sum))):
                        logger.warning(
                            "IDENTITY_MISMATCH_ADJ frame=%s year=%d base-additional=%.3f adj=%.3f",
                            cfg.deficits_frame,
                            y,
                            base_sum - add_sum,
                            adj_sum,
                        )
    except Exception:  # noqa: BLE001
        # Do not fail run on diagnostics issues
        pass

    return preview, base, adj


def build_deficits_preview_annual(preview_monthly: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate the expanded monthly preview to annual per frame (`year_key`).
    """
    cols_sum = [
        "gdp",
        "revenue_annual_usd_mn",
        "primary_outlays_annual_usd_mn",
        "additional_revenue_annual_usd_mn",
        "primary_deficit_base_annual_usd_mn",
        "primary_deficit_adj_annual_usd_mn",
    ]
    # Group by frame and year_key; frame is uniform but keep column for clarity
    grp = preview_monthly.groupby(["frame", "year_key"], as_index=False)[cols_sum].sum()
    # Derive shares as percent of GDP for the year
    def pct(col: str) -> pd.Series:
        return (grp[col] / grp["gdp"]) * 100.0
    grp["revenue_pct_gdp"] = pct("revenue_annual_usd_mn")
    grp["primary_outlays_pct_gdp"] = pct("primary_outlays_annual_usd_mn")
    grp["primary_deficit_base_pct_gdp"] = pct("primary_deficit_base_annual_usd_mn")
    grp["primary_deficit_adj_pct_gdp"] = pct("primary_deficit_adj_annual_usd_mn")
    # Order columns
    out = grp[[
        "frame", "year_key", "gdp",
        "revenue_pct_gdp", "revenue_annual_usd_mn",
        "primary_outlays_pct_gdp", "primary_outlays_annual_usd_mn",
        "additional_revenue_annual_usd_mn",
        "primary_deficit_base_pct_gdp", "primary_deficit_base_annual_usd_mn",
        "primary_deficit_adj_pct_gdp", "primary_deficit_adj_annual_usd_mn",
    ]].rename(columns={"year_key": "year"})
    return out


def write_deficits_preview(preview: pd.DataFrame, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    preview.to_csv(p, index=False)
    return p


def write_deficits_preview_annual(preview_annual: pd.DataFrame, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    preview_annual.to_csv(p, index=False)
    return p


