from __future__ import annotations

from pathlib import Path
import json
import math

import pytest

from macro.config import load_macro_yaml, write_config_echo


def write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_valid_config_loads_and_echo_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "macro.yaml"
    write_yaml(
        cfg_path,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
budget:
  frame: FY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
issuance_default_shares:
  short: 0.2
  nb: 0.7
  tips: 0.1
rates:
  type: constant
  values:
    short: 0.03
    nb: 0.04
    tips: 0.02
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
  annual_fy_growth_rate:
    2025: 4.0
    2026: 3.6
variable_rates_annual:
  short:
    2025: 4.25
    2026: 3.75
  nb:
    2025: 4.60
  tips:
    2025: 2.10
""",
    )

    cfg = load_macro_yaml(cfg_path)
    assert cfg.horizon_months == 24
    assert cfg.gdp_anchor_fy == 2025
    assert cfg.deficits_frame in {"FY", "CY"}
    # New fields present
    assert cfg.gdp_annual_fy_growth_rate is not None
    assert cfg.gdp_annual_fy_growth_rate[2025] == 4.0
    assert cfg.variable_rates_annual is not None
    assert cfg.variable_rates_annual["short"][2025] == 4.25

    out = write_config_echo(cfg, out_path=tmp_path / "config_echo.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["units"]["scale"] == "millions"
    assert data["gdp_anchor_value_usd_millions"] > 0
    assert set(data["issuance_default_shares"].keys()) == {"short", "nb", "tips"}
    # Echo includes new fields
    assert data["gdp_annual_fy_growth_rate"]["2025"] == 4.0
    assert data["variable_rates_annual"]["short"]["2025"] == 4.25


def test_missing_required_sections_raises(tmp_path: Path) -> None:
    cfg_path = tmp_path / "macro.yaml"
    write_yaml(
        cfg_path,
        """
anchor_date: 2025-07-01
horizon_months: 24
budget:
  frame: CY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
""",
    )
    with pytest.raises(ValueError):
        load_macro_yaml(cfg_path)


def test_shares_out_of_bounds_raises(tmp_path: Path) -> None:
    cfg_path = tmp_path / "macro.yaml"
    write_yaml(
        cfg_path,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 100.0
budget:
  frame: FY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
issuance_default_shares:
  short: 0.5
  nb: 0.6
  tips: -0.1
""",
    )
    with pytest.raises(ValueError):
        load_macro_yaml(cfg_path)


def test_non_finite_rates_raise(tmp_path: Path) -> None:
    cfg_path = tmp_path / "macro.yaml"
    # YAML supports .nan
    write_yaml(
        cfg_path,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 100.0
budget:
  frame: FY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
rates:
  type: constant
  values:
    short: .nan
    nb: 0.02
    tips: 0.01
""",
    )
    with pytest.raises(ValueError):
        load_macro_yaml(cfg_path)


def test_invalid_growth_map_raises(tmp_path: Path) -> None:
    cfg_path = tmp_path / "macro.yaml"
    write_yaml(
        cfg_path,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 100.0
  annual_fy_growth_rate:
    bad_year: 3.0
budget:
  frame: FY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
""",
    )
    with pytest.raises(ValueError):
        load_macro_yaml(cfg_path)


def test_invalid_variable_rates_annual_raises(tmp_path: Path) -> None:
    cfg_path = tmp_path / "macro.yaml"
    write_yaml(
        cfg_path,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 100.0
budget:
  frame: FY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
variable_rates_annual:
  short: 2.0  # must be mapping
""",
    )
    with pytest.raises(ValueError):
        load_macro_yaml(cfg_path)



