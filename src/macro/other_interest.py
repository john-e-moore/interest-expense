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


def build_other_interest_series(
    cfg: MacroConfig,
    gdp_model: GDPModel,
    index: pd.DatetimeIndex,
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    Convert other_interest config (percent of GDP or absolute USD) into a monthly USD series.

    Returns (series_monthly_usd_mn, preview_df)
    series indexed by month, units USD millions per month.
    preview columns: date, frame, year_key, mode, pct_gdp, annual_usd_mn, monthly_usd_mn
    """
    idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()

    # Choose frame: explicit other_interest_frame else fall back to deficits_frame
    frame = cfg.other_interest_frame or cfg.deficits_frame
    if frame not in {"FY", "CY"}:  # type: ignore[comparison-overlap]
        frame = "FY"

    # Select inputs
    pct_map = cfg.other_interest_annual_pct_gdp or {}
    abs_map = cfg.other_interest_annual_usd_mn or {}

    # Determine coverage years needed for frame
    if frame == "FY":
        years_needed = sorted(set([fiscal_year(d) for d in idx]))
    else:
        years_needed = sorted(set([d.year for d in idx]))

    pct_filled = _fill_year_map({int(k): float(v) for k, v in pct_map.items()}, years_needed)
    abs_filled = _fill_year_map({int(k): float(v) for k, v in abs_map.items()}, years_needed)
    abs_keys = set(int(k) for k in abs_map.keys())

    rows = []
    vals = []
    for d in idx:
        if frame == "FY":
            y = fiscal_year(d)
            gdp = float(gdp_model.gdp_fy(y))
        else:
            y = int(d.year)
            gdp = float(gdp_model.gdp_cy(y))

        # Compute annual USD: prefer absolute if provided for that year; else use pct-of-GDP
        abs_usd = float(abs_filled.get(int(y), 0.0))
        # Prefer ABS only if explicitly provided for the year
        if int(y) in abs_keys:
            annual = abs_usd
            mode = "ABS"
            pct_val = float(pct_filled.get(int(y), 0.0))
        else:
            pct_val = float(pct_filled.get(int(y), 0.0))
            annual = (pct_val / 100.0) * gdp
            mode = "PCT"

        mval = annual / 12.0
        vals.append(mval)
        rows.append(
            {
                "date": d,
                "frame": frame,
                "year_key": int(y),
                "mode": mode,
                "pct_gdp": pct_val,
                "annual_usd_mn": annual,
                "monthly_usd_mn": mval,
            }
        )

    series = pd.Series(vals, index=idx, name="other_interest")
    preview = pd.DataFrame(rows)
    return series, preview


def write_other_interest_preview(preview: pd.DataFrame, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    preview.to_csv(p, index=False)
    return p


