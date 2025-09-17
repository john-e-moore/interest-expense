from __future__ import annotations

from pathlib import Path

from scripts.run_forward import main as run_main


def write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_yaml_config_echo_is_byte_identical(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "macro.yaml"
    outdir = tmp_path / "out"
    content = (
        """
anchor_date: 2025-07-01
horizon_months: 12
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
budget:
  frame: FY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
  additional_revenue:
    enabled: true
    mode: level
    anchor_year: 2025
    anchor_amount: 100.0
    index: none
rates:
  type: constant
  values:
    short: 0.03
    nb: 0.04
    tips: 0.02
"""
    ).strip()
    write_yaml(cfg_path, content)

    import sys
    sys_argv = ["run_forward.py", "--config", str(cfg_path), "--outdir", str(outdir), "--dry-run"]
    monkeypatch.setattr("sys.argv", sys_argv)
    run_main()

    echoed = (outdir / "diagnostics" / "config_echo.yaml").read_text(encoding="utf-8")
    assert echoed == content
