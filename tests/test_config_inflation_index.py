from __future__ import annotations

from pathlib import Path
import pytest

from macro.config import load_macro_yaml


def write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_config_parses_inflation_and_anchor_level(tmp_path: Path) -> None:
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
  annual_revenue_pct_gdp: {2026: 18.0}
  annual_outlays_pct_gdp: {2026: 21.0}
  additional_revenue:
    enabled: true
    mode: level
    anchor_year: 2025
    anchor_amount: 100.0
    index: PCE
inflation:
  pce: {2026: 2.0, 2027: 3.0}
  cpi: {2026: 1.0, 2027: 1.5}
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
    assert cfg.additional_revenue_mode == "level"
    assert cfg.additional_revenue_anchor_year == 2025
    assert cfg.additional_revenue_anchor_amount == 100.0
    assert cfg.additional_revenue_index == "pce"
    assert cfg.inflation_pce == {2026: 2.0, 2027: 3.0}
    assert cfg.inflation_cpi == {2026: 1.0, 2027: 1.5}


def test_config_anchor_requires_triplet(tmp_path: Path) -> None:
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
  annual_revenue_pct_gdp: {2026: 18.0}
  annual_outlays_pct_gdp: {2026: 21.0}
  additional_revenue:
    enabled: true
    mode: level
    anchor_year: 2025
    index: none
inflation:
  pce: {2026: 2.0}
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


def test_config_rejects_unknown_index(tmp_path: Path) -> None:
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
  annual_revenue_pct_gdp: {2026: 18.0}
  annual_outlays_pct_gdp: {2026: 21.0}
  additional_revenue:
    enabled: true
    mode: level
    anchor_year: 2025
    anchor_amount: 100
    index: PCEE
inflation:
  pce: {2026: 2.0}
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
