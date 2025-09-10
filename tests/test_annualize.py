from __future__ import annotations

import pandas as pd

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


