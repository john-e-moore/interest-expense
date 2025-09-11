from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from diagnostics.qa import _compose_hist_vs_forward_series, run_qa
from macro.config import load_macro_yaml


def test_compose_hist_vs_forward_series_anchor_splice() -> None:
    # Build minimal monthly with interest_total and partial anchor-year months
    dates = pd.date_range("2025-06-01", periods=8, freq="MS")  # spans FY2025 and FY2026
    df = pd.DataFrame({
        "interest_total": [100, 100, 100, 100, 100, 100, 100, 100],
    }, index=dates)
    # Historical FY totals: full 2024, YTD 2025 (assume 2 months done for FY2025 for test)
    hist = pd.DataFrame({
        "Fiscal Year": [2024, 2025],
        "Interest Expense": [1200.0, 200.0],
    })
    # Anchor mid-2025
    anchor = pd.Timestamp("2025-07-15")
    hist_s, fwd_s, anchor_year = _compose_hist_vs_forward_series(df, hist, anchor_date=anchor, frame="FY")
    assert anchor_year == 2025
    # Historical should carry 2024 full and 2025 YTD
    assert hist_s.loc[2024] == 1200.0
    assert hist_s.loc[2025] == 200.0
    # Forward should include 2025 forward remainder only (months at/after anchor month)
    # For FY, remainder is months in anchor FY (Oct-Sep) at/after anchor month
    from core.dates import fiscal_year as _fy
    fwd_2025 = float(df.loc[(df.index >= anchor.to_period("M").to_timestamp()) & (df.index.map(_fy) == 2025), "interest_total"].sum())
    assert fwd_s.loc[2025] == fwd_2025
    # For FY 2026, include months in FY2026 (Oct 2025–Sep 2026) at/after anchor
    fy_2026_sum = float(df.loc[(df.index >= anchor.to_period("M").to_timestamp()) & (df.index.map(_fy) == 2026), "interest_total"].sum())
    assert fwd_s.loc[2026] == fy_2026_sum


def test_run_qa_writes_hist_vs_forward(tmp_path: Path) -> None:
    # Prepare minimal files expected by run_qa
    base = tmp_path
    (base / "diagnostics").mkdir(parents=True, exist_ok=True)
    # Minimal monthly trace CSV
    m = pd.DataFrame({
        "date": ["2025-07-01", "2025-08-01"],
        "stock_short": [1.0, 1.0],
        "stock_nb": [1.0, 1.0],
        "stock_tips": [1.0, 1.0],
        "interest_total": [10.0, 10.0],
        "other_interest": [0.0, 0.0],
    })
    m.to_csv(base / "diagnostics" / "monthly_trace.csv", index=False)
    # Annual CSVs
    (base / "calendar_year" / "spreadsheets").mkdir(parents=True, exist_ok=True)
    (base / "fiscal_year" / "spreadsheets").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"year": [2025], "interest": [20.0], "gdp": [100.0], "pct_gdp": [0.2]}).to_csv(base / "calendar_year" / "spreadsheets" / "annual.csv", index=False)
    pd.DataFrame({"year": [2025], "interest": [20.0], "gdp": [100.0], "pct_gdp": [0.2]}).to_csv(base / "fiscal_year" / "spreadsheets" / "annual.csv", index=False)
    # Historical totals
    pd.DataFrame({"Fiscal Year": [2025], "Interest Expense": [10.0]}).to_csv(base / "diagnostics" / "interest_fy_totals.csv", index=False)
    pd.DataFrame({"Calendar Year": [2025], "Interest Expense": [10.0]}).to_csv(base / "diagnostics" / "interest_cy_totals.csv", index=False)
    # Minimal config with anchor date
    cfg_text = """
anchor_date: 2025-07-15
horizon_months: 12
gdp:
  anchor_fy: 2025
  anchor_value_usd_millions: 28000000
deficits:
  frame: FY
rates:
  type: constant
  values:
    short: 0.01
    nb: 0.02
    tips: 0.01
issuance_default_shares:
  short: 0.2
  nb: 0.7
  tips: 0.1
"""
    (tmp_path / "macro.yaml").write_text(cfg_text)

    run_qa(
        monthly_trace_path=base / "diagnostics" / "monthly_trace.csv",
        annual_cy_path=base / "calendar_year" / "spreadsheets" / "annual.csv",
        annual_fy_path=base / "fiscal_year" / "spreadsheets" / "annual.csv",
        macro_path=tmp_path / "macro.yaml",
        out_base=base,
    )
    # New files should exist in FY and CY visualization folders
    fy_vis = base / "fiscal_year" / "visualizations"
    cy_vis = base / "calendar_year" / "visualizations"
    assert (fy_vis / "historical_vs_forward.png").exists()
    assert (cy_vis / "historical_vs_forward.png").exists()
    assert (fy_vis / "historical_vs_forward_pct_gdp.png").exists()
    assert (cy_vis / "historical_vs_forward_pct_gdp.png").exists()


