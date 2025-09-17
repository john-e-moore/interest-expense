from __future__ import annotations

import pandas as pd
import json

from annualize import annualize
from macro.gdp import build_gdp_function


def test_annualize_cy_fy_pct() -> None:
    # Build a simple monthly df with constant interest
    idx = pd.date_range("2025-07-01", periods=6, freq="MS")
    monthly = pd.DataFrame({"interest_total": [100.0] * len(idx)}, index=idx)

    gdp = build_gdp_function("2025-07-01", 30_000_000.0, {2026: 0.04, 2027: 0.03})
    cy, fy = annualize(monthly, gdp)

    # Interest sums match
    assert cy["interest"].sum() > 0
    assert fy["interest"].sum() > 0
    # %GDP finite and reasonable range
    assert (cy["pct_gdp"].between(0, 1)).all()
    assert (fy["pct_gdp"].between(0, 1)).all()


def test_annual_charts_labels_and_format(tmp_path: Path) -> None:
    # Create simple annual CSV
    years = [2024, 2025]
    df = pd.DataFrame({"year": years, "interest": [2_000_000.0, 3_000_000.0], "gdp": [50_000_000.0, 52_000_000.0]})
    df["pct_gdp"] = df["interest"] / df["gdp"]
    out_dir = tmp_path / "fiscal_year" / "visualizations"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv = tmp_path / "fiscal_year" / "spreadsheets" / "annual.csv"
    csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv, index=False)
    from diagnostics.qa import _plot_annual
    p = _plot_annual(csv, out_dir, "Annual FY Interest and %GDP")
    assert p.exists()
    meta = json.loads(p.with_suffix(".meta.json").read_text())
    assert meta["right_ylabel"] == "USD trillions"
    # Check at least one tick shows one decimal percent (e.g., '0.1%')
    assert any(("%" in t and "." in t) for t in meta["left_ticklabels"])


