from __future__ import annotations

import pandas as pd

from macro.config import MacroConfig
from macro.gdp import build_gdp_function
from macro.additional_revenue import build_additional_revenue_series


def _cfg(frame: str, mode: str, pct_map: dict[int, float] | None = None, lvl_map: dict[int, float] | None = None) -> MacroConfig:
    return MacroConfig(
        anchor_date=pd.Timestamp("2025-07-01").date(),
        horizon_months=14,
        gdp_anchor_fy=2025,
        gdp_anchor_value_usd_millions=30_353_902.0,
        budget_frame=frame,  # type: ignore[arg-type]
        budget_annual_revenue_pct_gdp={},
        budget_annual_outlays_pct_gdp={},
        additional_revenue_mode=mode,  # type: ignore[arg-type]
        additional_revenue_annual_pct_gdp=pct_map,
        additional_revenue_annual_level_usd_millions=lvl_map,
        issuance_default_shares=None,
        rates_constant=(0.03, 0.04, 0.02),
        gdp_annual_fy_growth_rate={2026: 0.0, 2027: 0.0},
        variable_rates_annual=None,
    )


def test_additional_revenue_pct_fy_partial_anchor() -> None:
    # Index from 2025-07 to 2026-06 (FY2025 has 3 months; FY2026 has 9 months in index)
    idx = pd.date_range("2025-07-01", periods=12, freq="MS")
    cfg = _cfg("FY", "pct_gdp", {2025: 1.0, 2026: 1.1}, None)
    gdp = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.0, 2027: 0.0})
    s, prev = build_additional_revenue_series(cfg, gdp, idx)
    assert len(s) == len(idx)
    a25 = (1.0 / 100.0) * gdp.gdp_fy(2025)
    a26 = (1.1 / 100.0) * gdp.gdp_fy(2026)
    fy25_mask = prev["year_key"] == 2025
    fy26_mask = prev["year_key"] == 2026
    assert abs(prev.loc[fy25_mask, "additional_revenue_month_usd_mn"].sum() - a25 * 3 / 12) < 1e-6
    assert abs(prev.loc[fy26_mask, "additional_revenue_month_usd_mn"].sum() - a26 * 9 / 12) < 1e-6


def test_additional_revenue_level_cy_full_year() -> None:
    idx = pd.date_range("2026-01-01", periods=12, freq="MS")
    cfg = _cfg("CY", "level", None, {2026: 6000.0})
    gdp = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.0, 2027: 0.0})
    s, prev = build_additional_revenue_series(cfg, gdp, idx)
    assert abs(s.sum() - 6000.0) < 1e-6
    assert abs(prev["additional_revenue_month_usd_mn"].iloc[0] - (6000.0 / 12.0)) < 1e-9


