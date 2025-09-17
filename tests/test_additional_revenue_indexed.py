from __future__ import annotations

from pathlib import Path
import pandas as pd

from scripts.run_forward import main as run_main


def write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_builder_level_indexed_and_diagnostics(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "macro.yaml"
    outdir = tmp_path / "out"
    write_yaml(
        cfg_path,
        """
anchor_date: 2025-07-01
horizon_months: 12
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
  annual_fy_growth_rate:
    2025: 0.0
    2026: 0.0
budget:
  frame: FY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
  additional_revenue:
    enabled: true
    mode: level
    anchor_year: 2025
    anchor_amount: 100.0
    index: PCE
inflation:
  pce: {2026: 2.0, 2027: 3.0}
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

    import sys
    sys_argv = ["run_forward.py", "--config", str(cfg_path), "--outdir", str(outdir)]
    monkeypatch.setattr("sys.argv", sys_argv)
    run_main()

    infl_prev = outdir / "diagnostics" / "inflation_index_preview.csv"
    assert infl_prev.exists()
    df = pd.read_csv(infl_prev)
    # Anchor year 2025 factor = 1.0 and value = 100
    row_2025 = df[df["year_key"] == 2025].iloc[0]
    assert abs(row_2025["cumulative_factor"] - 1.0) < 1e-9
    assert abs(row_2025["indexed_value_unit"] - 100.0) < 1e-9
    # 2026 factor = 1.02, value = 102
    row_2026 = df[df["year_key"] == 2026].iloc[0]
    assert abs(row_2026["cumulative_factor"] - 1.02) < 1e-9
    assert abs(row_2026["indexed_value_unit"] - 102.0) < 1e-6


def test_builder_pct_gdp_indexed_preview_extended(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "macro.yaml"
    outdir = tmp_path / "out"
    write_yaml(
        cfg_path,
        """
anchor_date: 2025-07-01
horizon_months: 12
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 30000000
  annual_fy_growth_rate:
    2025: 0.0
    2026: 0.0
budget:
  frame: FY
  annual_revenue_pct_gdp: {2025: 18.0}
  annual_outlays_pct_gdp: {2025: 21.0}
  additional_revenue:
    enabled: true
    mode: pct_gdp
    anchor_year: 2025
    anchor_amount: 1.0
    index: CPI
inflation:
  cpi: {2026: 2.0}
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

    import sys
    sys_argv = ["run_forward.py", "--config", str(cfg_path), "--outdir", str(outdir)]
    monkeypatch.setattr("sys.argv", sys_argv)
    run_main()

    add_prev = outdir / "diagnostics" / "additional_revenue_preview.csv"
    assert add_prev.exists()
    df = pd.read_csv(add_prev)
    # Columns extended
    for col in ["index", "anchor_year", "anchor_amount", "inflation_rate_pct", "cumulative_factor"]:
        assert col in df.columns
