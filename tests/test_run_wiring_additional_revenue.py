from __future__ import annotations

from pathlib import Path
import pandas as pd

from scripts.run_forward import main as run_main


def write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_run_wiring_with_additional_revenue_pct(tmp_path: Path, monkeypatch) -> None:
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
deficits:
  frame: FY
  annual_pct_gdp:
    2025: 3.0
  additional_revenue:
    mode: pct_gdp
    annual_pct_gdp:
      2025: 1.0
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

    # Run main with args
    import sys
    sys_argv = ["run_forward.py", "--config", str(cfg_path), "--outdir", str(outdir)]
    monkeypatch.setattr("sys.argv", sys_argv)
    run_main()

    trace = outdir / "diagnostics" / "monthly_trace.parquet"
    assert trace.exists()
    df = pd.read_parquet(trace)
    # Columns should include enrichment
    assert "primary_deficit_base" in df.columns
    assert "additional_revenue" in df.columns
    assert "primary_deficit_adj" in df.columns
    # Base deficit should be larger than adjusted when additional revenue is positive
    assert (df["primary_deficit_base"] >= df["primary_deficit_adj"]).all()


