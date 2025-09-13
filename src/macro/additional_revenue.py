from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

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


def build_additional_revenue_series(
    cfg: MacroConfig,
    gdp_model: GDPModel,
    index: pd.DatetimeIndex,
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    Build monthly additional revenue (USD millions per month) from annual inputs.

    Modes:
      - pct_gdp: use percentages (not decimals) of FY/CY GDP
      - level:   use annual USD millions directly

    Returns (series_monthly_usd_mn, preview_df)
    series indexed by month, name 'additional_revenue'.
    preview columns: date, frame, year_key, mode, input_value, gdp, additional_revenue_annual_usd_mn, additional_revenue_month_usd_mn
    """
    mode = getattr(cfg, "additional_revenue_mode", None)
    if mode is None:
        raise ValueError("additional_revenue not configured (mode is None)")

    idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()

    # Determine coverage years needed for frame
    if cfg.deficits_frame == "FY":
        years_needed = sorted(set([fiscal_year(d) for d in idx]))
    else:
        years_needed = sorted(set([d.year for d in idx]))

    rows = []
    vals = []

    if mode == "pct_gdp":
        pct_map = getattr(cfg, "additional_revenue_annual_pct_gdp", None) or {}
        pct_filled = _fill_year_map({int(k): float(v) for k, v in pct_map.items()}, years_needed)
        for d in idx:
            if cfg.deficits_frame == "FY":
                y = fiscal_year(d)
                gdp = float(gdp_model.gdp_fy(y))
            else:
                y = int(d.year)
                gdp = float(gdp_model.gdp_cy(y))
            pct = float(pct_filled.get(int(y), 0.0))
            annual = (pct / 100.0) * gdp
            mval = annual / 12.0
            vals.append(mval)
            rows.append(
                {
                    "date": d,
                    "frame": cfg.deficits_frame,
                    "year_key": int(y),
                    "mode": mode,
                    "input_value": pct,
                    "gdp": gdp,
                    "additional_revenue_annual_usd_mn": annual,
                    "additional_revenue_month_usd_mn": mval,
                }
            )
    elif mode == "level":
        lvl_map = getattr(cfg, "additional_revenue_annual_level_usd_millions", None) or {}
        lvl_filled = _fill_year_map({int(k): float(v) for k, v in lvl_map.items()}, years_needed)
        for d in idx:
            if cfg.deficits_frame == "FY":
                y = fiscal_year(d)
            else:
                y = int(d.year)
            annual = float(lvl_filled.get(int(y), 0.0))
            mval = annual / 12.0
            vals.append(mval)
            rows.append(
                {
                    "date": d,
                    "frame": cfg.deficits_frame,
                    "year_key": int(y),
                    "mode": mode,
                    "input_value": annual,
                    "gdp": float("nan"),
                    "additional_revenue_annual_usd_mn": annual,
                    "additional_revenue_month_usd_mn": mval,
                }
            )
    else:
        raise ValueError("additional_revenue.mode must be 'pct_gdp' or 'level'")

    series = pd.Series(vals, index=idx, name="additional_revenue")
    preview = pd.DataFrame(rows)
    return series, preview


def write_additional_revenue_preview(preview: pd.DataFrame, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    preview.to_csv(p, index=False)
    return p



