from __future__ import annotations

import pandas as pd

from macro.config import MacroConfig
from macro.gdp import build_gdp_function
from macro.budget import build_budget_component_series, build_deficits_preview_monthly, build_deficits_preview_annual


def _cfg(frame: str, rev: dict[int, float], out: dict[int, float]) -> MacroConfig:
    return MacroConfig(
        anchor_date=pd.Timestamp("2025-07-01").date(),
        horizon_months=14,
        gdp_anchor_fy=2025,
        gdp_anchor_value_usd_millions=30_000_000.0,
        budget_frame=frame,  # type: ignore[arg-type]
        budget_annual_revenue_pct_gdp=rev,
        budget_annual_outlays_pct_gdp=out,
        additional_revenue_mode=None,
        additional_revenue_annual_pct_gdp=None,
        additional_revenue_annual_level_usd_millions=None,
        additional_revenue_enabled=False,
        inflation_pce=None,
        inflation_cpi=None,
        other_interest_enabled=True,
        other_interest_frame=None,
        other_interest_annual_pct_gdp=None,
        other_interest_annual_usd_mn=None,
        issuance_transition_enabled=True,
        issuance_transition_months=6,
        issuance_default_shares=None,
        rates_constant=(0.03, 0.04, 0.02),
        gdp_annual_fy_growth_rate={2026: 4.0},
        variable_rates_annual=None,
    )


def test_build_components_and_previews_fy() -> None:
    # Months Jul25..Jun26 (FY2025 has 3 months; FY2026 has 9 months)
    idx = pd.date_range("2025-07-01", periods=12, freq="MS")
    cfg = _cfg("FY", {2025: 18.0, 2026: 18.0}, {2025: 21.0, 2026: 21.0})
    gdp = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.0})
    rev, out, preview_components = build_budget_component_series(cfg, gdp, idx)
    assert len(rev) == len(idx)
    assert len(out) == len(idx)
    # Annual checks: revenue share times GDP equals 12 * monthly
    r25_ann = 0.18 * gdp.gdp_fy(2025)
    r26_ann = 0.18 * gdp.gdp_fy(2026)
    mask25 = preview_components["year_key"] == 2025
    mask26 = preview_components["year_key"] == 2026
    assert abs(preview_components.loc[mask25, "revenue_month_usd_mn"].sum() - r25_ann * 3 / 12) < 1e-6
    assert abs(preview_components.loc[mask26, "revenue_month_usd_mn"].sum() - r26_ann * 9 / 12) < 1e-6

    # Build expanded monthly and annual previews
    monthly, base, adj = build_deficits_preview_monthly(cfg, gdp, idx, rev, out, None)
    assert len(monthly) == len(idx)
    assert (adj - base).abs().max() < 1e-12
    annual = build_deficits_preview_annual(monthly)
    # Annual primary deficit share should be outlays-revenue
    for _, row in annual.iterrows():
        assert abs(row["primary_deficit_base_pct_gdp"] - (row["primary_outlays_pct_gdp"] - row["revenue_pct_gdp"])) < 1e-6


def test_build_components_cy_sum_to_cy_gdp() -> None:
    idx = pd.date_range("2026-01-01", periods=12, freq="MS")
    cfg = _cfg("CY", {2026: 18.0}, {2026: 21.0})
    gdp = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.0, 2027: 0.0})
    rev, out, preview_components = build_budget_component_series(cfg, gdp, idx)
    # Annual CY totals equal the CY GDP share
    r_cy = 0.18 * gdp.gdp_cy(2026)
    o_cy = 0.21 * gdp.gdp_cy(2026)
    assert abs(rev.sum() - r_cy) < 1e-6
    assert abs(out.sum() - o_cy) < 1e-6


