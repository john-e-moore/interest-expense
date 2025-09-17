from __future__ import annotations

import pandas as pd

from macro.config import MacroConfig
from macro.gdp import build_gdp_function
from macro.budget import build_budget_component_series, build_deficits_preview_monthly


def _cfg(frame: str, pct_map: dict[int, float]) -> MacroConfig:
    # Minimal MacroConfig stub values
    return MacroConfig(
        anchor_date=pd.Timestamp("2025-07-01").date(),
        horizon_months=14,
        gdp_anchor_fy=2025,
        gdp_anchor_value_usd_millions=30_353_902.0,
        budget_frame=frame,  # type: ignore[arg-type]
        budget_annual_revenue_pct_gdp={y: 0.0 for y in pct_map},
        budget_annual_outlays_pct_gdp=pct_map,
        issuance_default_shares=None,
        rates_constant=(0.03, 0.04, 0.02),
        gdp_annual_fy_growth_rate={2026: 0.04},
        variable_rates_annual=None,
    )


def test_build_primary_deficit_series_fy_mapping_partial_anchor() -> None:
    # Index from 2025-07 to 2026-06 (FY2025 has 3 months; FY2026 has 12 months)
    idx = pd.date_range("2025-07-01", periods=12, freq="MS")
    cfg = _cfg("FY", {2025: 3.0, 2026: 2.8})
    gdp_model = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.04})

    revenue, outlays, components = build_budget_component_series(cfg, gdp_model, idx)
    preview, base, _adj = build_deficits_preview_monthly(cfg, gdp_model, idx, revenue, outlays, None)
    assert len(base) == len(idx)
    # Annual targets
    d25_annual = (3.0 / 100.0) * gdp_model.gdp_fy(2025)
    d26_annual = (2.8 / 100.0) * gdp_model.gdp_fy(2026)
    # FY2025 months present in index: Jul, Aug, Sep -> 3/12 of annual
    fy25_mask = preview["year_key"] == 2025
    fy26_mask = preview["year_key"] == 2026
    assert abs(preview.loc[fy25_mask, "deficit_month_usd_mn"].sum() - (d25_annual * 3 / 12)) < 1e-6
    # Our idx is 2025-07..2026-06, so FY2026 months present = Oct..Jun = 9 months
    assert abs(preview.loc[fy26_mask, "primary_deficit_base_month_usd_mn"].sum() - (d26_annual * 9 / 12)) < 1e-6


def test_build_primary_deficit_series_cy_mapping() -> None:
    # Calendar year mapping: Jan..Dec
    idx = pd.date_range("2026-01-01", periods=12, freq="MS")
    cfg = _cfg("CY", {2026: 2.5})
    # Provide growth for 2026 and 2027 since CY uses FY(y) and FY(y+1)
    gdp_model = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.0, 2027: 0.0})
    revenue, outlays, _components = build_budget_component_series(cfg, gdp_model, idx)
    _preview, base, _adj = build_deficits_preview_monthly(cfg, gdp_model, idx, revenue, outlays, None)
    d26_cy = (2.5 / 100.0) * gdp_model.gdp_cy(2026)
    assert abs(base.sum() - d26_cy) < 1e-6


