from __future__ import annotations

from pathlib import Path
import json

from macro.config import load_macro_yaml, write_config_echo


def write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_budget_schema_parses_and_echo_contains_budget(tmp_path: Path) -> None:
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
  annual_revenue_pct_gdp:
    2026: 18.0
  annual_outlays_pct_gdp:
    2026: 21.0
  additional_revenue:
    enabled: true
    mode: level
    anchor_year: 2026
    anchor_amount: 100.0
    index: none
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
""",
    )

    cfg = load_macro_yaml(cfg_path)
    assert cfg.budget_frame == "FY"
    assert cfg.budget_annual_revenue_pct_gdp == {2026: 18.0}
    assert cfg.budget_annual_outlays_pct_gdp == {2026: 21.0}
    assert cfg.additional_revenue_enabled is True
    assert cfg.additional_revenue_mode == "level"
    assert cfg.additional_revenue_anchor_year == 2026
    assert cfg.additional_revenue_anchor_amount == 100.0
    assert cfg.additional_revenue_index == "none"

    out = write_config_echo(cfg, out_path=tmp_path / "config_echo.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "budget" in data
    assert data["budget"]["frame"] == "FY"
    assert data["budget"]["annual_revenue_pct_gdp"]["2026"] == 18.0
    assert data["budget"]["annual_outlays_pct_gdp"]["2026"] == 21.0
    assert data["budget"]["additional_revenue"]["anchor_year"] == 2026


def test_budget_requires_both_share_maps(tmp_path: Path) -> None:
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
  frame: CY
  annual_revenue_pct_gdp:
    2026: 18.0
rates:
  type: constant
  values:
    short: 0.03
    nb: 0.04
    tips: 0.02
""",
    )
    import pytest

    with pytest.raises(ValueError):
        load_macro_yaml(cfg_path)


