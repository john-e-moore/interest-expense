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


def build_primary_deficit_series(
    cfg: MacroConfig,
    gdp_model: GDPModel,
    index: pd.DatetimeIndex,
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    Convert annual primary deficits (percent of GDP) into a monthly USD series over index.

    Returns (series_monthly_usd_mn, preview_df)
    series indexed by month, units USD millions per month.
    preview columns: date, frame, year_key, pct_gdp, gdp, deficit_month_usd_mn, deficit_annual_usd_mn
    """
    idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()

    pct_map = cfg.deficits_annual_pct_gdp or {}
    # Determine coverage years needed for frame
    if cfg.deficits_frame == "FY":
        years_needed = sorted(set([fiscal_year(d) for d in idx]))
    else:
        years_needed = sorted(set([d.year for d in idx]))
    pct_filled = _fill_year_map({int(k): float(v) for k, v in pct_map.items()}, years_needed)

    # Build per-month values
    rows = []
    vals = []
    for d in idx:
        if cfg.deficits_frame == "FY":
            y = fiscal_year(d)
            gdp = float(gdp_model.gdp_fy(y))
        else:
            y = int(d.year)
            gdp = float(gdp_model.gdp_cy(y))
        pct = float(pct_filled.get(int(y), 0.0))
        pct_decimal = pct / 100.0
        annual = pct_decimal * gdp
        mval = annual / 12.0
        vals.append(mval)
        rows.append(
            {
                "date": d,
                "frame": cfg.deficits_frame,
                "year_key": int(y),
                "pct_gdp": pct,
                "gdp": gdp,
                "deficit_annual_usd_mn": annual,
                "deficit_month_usd_mn": mval,
            }
        )

    series = pd.Series(vals, index=idx, name="primary_deficit")
    preview = pd.DataFrame(rows)
    return series, preview


def write_deficits_preview(preview: pd.DataFrame, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    preview.to_csv(p, index=False)
    return p


