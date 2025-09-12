from __future__ import annotations

import pandas as pd

from macro.config import MacroConfig
from macro.gdp import build_gdp_function
from macro.deficits import build_primary_deficit_series


def _cfg(frame: str, pct_map: dict[int, float]) -> MacroConfig:
    # Minimal MacroConfig stub values
    return MacroConfig(
        anchor_date=pd.Timestamp("2025-07-01").date(),
        horizon_months=14,
        gdp_anchor_fy=2025,
        gdp_anchor_value_usd_millions=30_353_902.0,
        deficits_frame=frame,  # type: ignore[arg-type]
        deficits_annual_pct_gdp=pct_map,
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

    series, preview = build_primary_deficit_series(cfg, gdp_model, idx)
    assert len(series) == len(idx)
    # Annual targets
    d25_annual = (3.0 / 100.0) * gdp_model.gdp_fy(2025)
    d26_annual = (2.8 / 100.0) * gdp_model.gdp_fy(2026)
    # FY2025 months present in index: Jul, Aug, Sep -> 3/12 of annual
    fy25_mask = preview["year_key"] == 2025
    fy26_mask = preview["year_key"] == 2026
    assert abs(preview.loc[fy25_mask, "deficit_month_usd_mn"].sum() - (d25_annual * 3 / 12)) < 1e-6
    # Full FY2026 covered (if index spans Oct25..Sep26; adjust: our idx covers Oct25..Jun26 = 9 months)
    # Here our index is 2025-07..2026-06, so FY2026 months present = Oct..Jun = 9 months
    assert abs(preview.loc[fy26_mask, "deficit_month_usd_mn"].sum() - (d26_annual * 9 / 12)) < 1e-6


def test_build_primary_deficit_series_cy_mapping() -> None:
    # Calendar year mapping: Jan..Dec
    idx = pd.date_range("2026-01-01", periods=12, freq="MS")
    cfg = _cfg("CY", {2026: 2.5})
    # Provide growth for 2026 and 2027 since CY uses FY(y) and FY(y+1)
    gdp_model = build_gdp_function(cfg.anchor_date, cfg.gdp_anchor_value_usd_millions, {2026: 0.0, 2027: 0.0})
    series, preview = build_primary_deficit_series(cfg, gdp_model, idx)
    d26_cy = (2.5 / 100.0) * gdp_model.gdp_cy(2026)
    assert abs(series.sum() - d26_cy) < 1e-6


