from __future__ import annotations

from pathlib import Path
import pytest

from macro.config import load_macro_yaml


def write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_config_parses_additional_revenue_pct(tmp_path: Path) -> None:
    p = tmp_path / "macro.yaml"
    write_yaml(
        p,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
budget:
  frame: FY
  annual_revenue_pct_gdp:
    2026: 18.0
  annual_outlays_pct_gdp:
    2026: 21.0
  additional_revenue:
    enabled: true
    mode: pct_gdp
    annual_pct_gdp:
      2026: 1.0
rates:
  type: constant
  values:
    short: 0.03
    nb: 0.04
    tips: 0.02
""",
    )
    cfg = load_macro_yaml(p)
    assert cfg.additional_revenue_enabled is True
    assert cfg.additional_revenue_mode == "pct_gdp"
    assert cfg.additional_revenue_annual_pct_gdp == {2026: 1.0}
    assert cfg.additional_revenue_annual_level_usd_millions is None


def test_config_parses_additional_revenue_level(tmp_path: Path) -> None:
    p = tmp_path / "macro.yaml"
    write_yaml(
        p,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
budget:
  frame: CY
  annual_revenue_pct_gdp:
    2026: 18.0
  annual_outlays_pct_gdp:
    2026: 21.0
  additional_revenue:
    enabled: true
    mode: level
    annual_level_usd_millions:
      2026: 300000
rates:
  type: constant
  values:
    short: 0.03
    nb: 0.04
    tips: 0.02
""",
    )
    cfg = load_macro_yaml(p)
    assert cfg.deficits_frame == "CY"
    assert cfg.additional_revenue_enabled is True
    assert cfg.additional_revenue_mode == "level"
    assert cfg.additional_revenue_annual_level_usd_millions == {2026: 300000.0}


def test_config_additional_revenue_requires_matching_map_when_enabled(tmp_path: Path) -> None:
    p = tmp_path / "macro.yaml"
    write_yaml(
        p,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
budget:
  frame: FY
  annual_revenue_pct_gdp:
    2026: 18.0
  annual_outlays_pct_gdp:
    2026: 21.0
  additional_revenue:
    enabled: true
    mode: level
    annual_pct_gdp:
      2026: 1.0
rates:
  type: constant
  values:
    short: 0.03
    nb: 0.04
    tips: 0.02
""",
    )
    with pytest.raises(ValueError):
        load_macro_yaml(p)


def test_config_additional_revenue_default_disabled(tmp_path: Path) -> None:
    p = tmp_path / "macro.yaml"
    write_yaml(
        p,
        """
anchor_date: 2025-07-01
horizon_months: 24
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
budget:
  frame: FY
  annual_revenue_pct_gdp:
    2026: 18.0
  annual_outlays_pct_gdp:
    2026: 21.0
  additional_revenue:
    mode: level
    annual_level_usd_millions:
      2026: 300000
rates:
  type: constant
  values:
    short: 0.03
    nb: 0.04
    tips: 0.02
""",
    )
    cfg = load_macro_yaml(p)
    assert cfg.additional_revenue_enabled is False
    assert cfg.additional_revenue_mode == "level"


