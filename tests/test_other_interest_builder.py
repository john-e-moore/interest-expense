from __future__ import annotations

import pandas as pd

from macro.config import MacroConfig
from macro.gdp import build_gdp_function
from macro.other_interest import build_other_interest_series


def _cfg(frame: str, pct_map: dict[int, float] | None = None, abs_map: dict[int, float] | None = None) -> MacroConfig:
    return MacroConfig(
        anchor_date=pd.Timestamp("2025-07-01").date(),
        horizon_months=14,
        gdp_anchor_fy=2025,
        gdp_anchor_value_usd_millions=30_353_902.0,
        deficits_frame="FY",  # irrelevant here
        deficits_annual_pct_gdp=None,
        other_interest_enabled=True,
        other_interest_frame=frame,  # type: ignore[arg-type]
        other_interest_annual_pct_gdp=pct_map,
        other_interest_annual_usd_mn=abs_map,
        issuance_default_shares=None,
        rates_constant=(0.03, 0.04, 0.02),
        gdp_annual_fy_growth_rate={2026: 0.0, 2027: 0.0},
        variable_rates_annual=None,
    )


def test_other_interest_pct_fy_partial_anchor() -> None:
    idx = pd.date_range("2025-07-01", periods=12, freq="MS")
    cfg = _cfg("FY", {2025: 0.2, 2026: 0.18})
    gdp = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.0, 2027: 0.0})
    s, prev = build_other_interest_series(cfg, gdp, idx)
    a25 = (0.2 / 100.0) * gdp.gdp_fy(2025)
    a26 = (0.18 / 100.0) * gdp.gdp_fy(2026)
    assert abs(prev.loc[prev.year_key == 2025, "monthly_usd_mn"].sum() - a25 * 3 / 12) < 1e-6
    assert abs(prev.loc[prev.year_key == 2026, "monthly_usd_mn"].sum() - a26 * 9 / 12) < 1e-6


def test_other_interest_abs_cy_full_year() -> None:
    idx = pd.date_range("2026-01-01", periods=12, freq="MS")
    cfg = _cfg("CY", None, {2026: 6000.0})
    gdp = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.0, 2027: 0.0})
    s, prev = build_other_interest_series(cfg, gdp, idx)
    assert abs(s.sum() - 6000.0) < 1e-6

