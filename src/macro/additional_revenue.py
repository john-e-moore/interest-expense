from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, List, Optional

import pandas as pd

from core.dates import fiscal_year
from macro.config import MacroConfig
from macro.gdp import GDPModel
def _compute_cumulative_factors(
    years: List[int],
    anchor_year: int,
    index_kind: str,
    pce: Optional[Dict[int, float]],
    cpi: Optional[Dict[int, float]],
) -> Dict[int, float]:
    """Compute forward-only cumulative factors by year.

    factor[anchor_year] = 1.0
    For year > anchor_year: Π(1 + I_y/100) from (anchor_year+1..year)
    For year < anchor_year: 1.0 (no back-indexing)
    If index_kind == "none": 1.0 for all years.
    """
    idx = index_kind.lower()
    if idx not in {"none", "pce", "cpi"}:
        idx = "none"
    factors: Dict[int, float] = {}
    if idx == "none":
        for y in years:
            factors[y] = 1.0
        return factors

    series = (pce or {}) if idx == "pce" else (cpi or {})
    # Pre-fill rates by carrying last known forward for requested years
    all_years = sorted(set(years + list(series.keys())))
    carried: Dict[int, float] = {}
    last = float(series.get(min(series.keys()) if series else (anchor_year + 1), 0.0))
    for y in all_years:
        if y in series:
            last = float(series[y])
        carried[y] = last

    # Build cumulative product from anchor_year+1 upward
    cumulative = 1.0
    for y in sorted(all_years):
        if y <= anchor_year:
            continue
        rate_pct = float(carried.get(y, 0.0))
        cumulative *= (1.0 + (rate_pct / 100.0))
        if y in years:
            factors[y] = cumulative

    # Ensure all requested years have entries
    for y in years:
        if y == anchor_year:
            factors[y] = 1.0
        elif y < anchor_year and y not in factors:
            factors[y] = 1.0
        elif y > anchor_year and y not in factors:
            # If beyond provided series, keep last cumulative
            factors[y] = cumulative if cumulative != 0.0 else 1.0
    return factors


def build_inflation_index_preview(
    cfg: MacroConfig,
    years_needed: List[int],
    mode: str,
) -> Optional[pd.DataFrame]:
    """Build per-year inflation indexing diagnostics for anchor+index configs.

    Returns a DataFrame or None if anchor+index is not configured.
    Columns: frame, year_key, mode, index, anchor_year, anchor_amount,
             inflation_source, inflation_rate_pct, cumulative_factor, indexed_value_unit
    """
    anchor_year = getattr(cfg, "additional_revenue_anchor_year", None)
    anchor_amount = getattr(cfg, "additional_revenue_anchor_amount", None)
    index_kind = getattr(cfg, "additional_revenue_index", None)
    if anchor_year is None or anchor_amount is None or index_kind is None:
        return None

    pce = getattr(cfg, "inflation_pce", None)
    cpi = getattr(cfg, "inflation_cpi", None)
    factors = _compute_cumulative_factors(years_needed, int(anchor_year), str(index_kind), pce, cpi)

    rows = []
    for y in years_needed:
        rate_map = pce if str(index_kind).lower() == "pce" else cpi if str(index_kind).lower() == "cpi" else {}
        rate_pct = 0.0
        if str(index_kind).lower() in {"pce", "cpi"} and y > int(anchor_year):
            rate_pct = float((rate_map or {}).get(int(y), 0.0))
        indexed_val = float(anchor_amount) * float(factors.get(int(y), 1.0)) if y >= int(anchor_year) else float(anchor_amount)
        rows.append(
            {
                "frame": cfg.deficits_frame,
                "year_key": int(y),
                "mode": mode,
                "index": str(index_kind).lower(),
                "anchor_year": int(anchor_year),
                "anchor_amount": float(anchor_amount),
                "inflation_source": ("PCE" if str(index_kind).lower() == "pce" else "CPI" if str(index_kind).lower() == "cpi" else "None"),
                "inflation_rate_pct": float(rate_pct),
                "cumulative_factor": float(factors.get(int(y), 1.0)),
                "indexed_value_unit": float(indexed_val),
            }
        )
    return pd.DataFrame(rows)


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

    # Prefer anchor+index if provided
    anchor_year = getattr(cfg, "additional_revenue_anchor_year", None)
    anchor_amount = getattr(cfg, "additional_revenue_anchor_amount", None)
    index_kind = getattr(cfg, "additional_revenue_index", None)
    used_anchor_index = False

    if anchor_year is not None and anchor_amount is not None and index_kind is not None:
        used_anchor_index = True
        # Build per-year indexed series in mode units
        if mode == "pct_gdp":
            # Percent-of-GDP values per year
            factors = _compute_cumulative_factors(
                years_needed,
                int(anchor_year),
                str(index_kind),
                getattr(cfg, "inflation_pce", None),
                getattr(cfg, "inflation_cpi", None),
            )
            pct_map_indexed = {int(y): (float(anchor_amount) * float(factors.get(int(y), 1.0)) if y >= int(anchor_year) else float(anchor_amount)) for y in years_needed}
            for d in idx:
                if cfg.deficits_frame == "FY":
                    y = fiscal_year(d)
                    gdp = float(gdp_model.gdp_fy(y))
                else:
                    y = int(d.year)
                    gdp = float(gdp_model.gdp_cy(y))
                pct = float(pct_map_indexed.get(int(y), 0.0))
                annual = (pct / 100.0) * gdp
                mval = annual / 12.0
                vals.append(mval)
                # For diagnostics, include inflation context
                rate_map = getattr(cfg, "inflation_pce", None) if str(index_kind).lower() == "pce" else getattr(cfg, "inflation_cpi", None) if str(index_kind).lower() == "cpi" else None
                rate_pct = 0.0 if int(y) <= int(anchor_year) or rate_map is None else float(rate_map.get(int(y), 0.0))
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
                        "index": str(index_kind).lower(),
                        "anchor_year": int(anchor_year),
                        "anchor_amount": float(anchor_amount),
                        "inflation_rate_pct": float(rate_pct),
                        "cumulative_factor": float(factors.get(int(y), 1.0)),
                    }
                )
        elif mode == "level":
            # USD millions per year
            factors = _compute_cumulative_factors(
                years_needed,
                int(anchor_year),
                str(index_kind),
                getattr(cfg, "inflation_pce", None),
                getattr(cfg, "inflation_cpi", None),
            )
            lvl_map_indexed = {int(y): (float(anchor_amount) * float(factors.get(int(y), 1.0)) if y >= int(anchor_year) else float(anchor_amount)) for y in years_needed}
            for d in idx:
                if cfg.deficits_frame == "FY":
                    y = fiscal_year(d)
                else:
                    y = int(d.year)
                annual = float(lvl_map_indexed.get(int(y), 0.0))
                mval = annual / 12.0
                vals.append(mval)
                rate_map = getattr(cfg, "inflation_pce", None) if str(index_kind).lower() == "pce" else getattr(cfg, "inflation_cpi", None) if str(index_kind).lower() == "cpi" else None
                rate_pct = 0.0 if int(y) <= int(anchor_year) or rate_map is None else float(rate_map.get(int(y), 0.0))
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
                        "index": str(index_kind).lower(),
                        "anchor_year": int(anchor_year),
                        "anchor_amount": float(anchor_amount),
                        "inflation_rate_pct": float(rate_pct),
                        "cumulative_factor": float(factors.get(int(y), 1.0)),
                    }
                )
        else:
            raise ValueError("additional_revenue.mode must be 'pct_gdp' or 'level'")
    elif mode == "pct_gdp":
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


def write_inflation_index_preview(preview: pd.DataFrame, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    preview.to_csv(p, index=False)
    return p



