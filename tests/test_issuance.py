from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from macro.issuance import FixedSharesPolicy, PiecewiseSharesPolicy, write_issuance_preview
from macro.rates import build_month_index


def test_fixed_shares_sum_to_one_and_shape() -> None:
    idx = build_month_index("2025-07-01", 6)
    pol = FixedSharesPolicy(0.2, 0.7, 0.1)
    df = pol.get(idx)
    assert df.shape == (6, 3)
    assert abs(df.iloc[0].sum() - 1.0) < 1e-9


def test_fixed_shares_bounds_validation() -> None:
    with pytest.raises(ValueError):
        FixedSharesPolicy(0.7, 0.5, -0.2)


def test_piecewise_behavior_changes_over_time() -> None:
    idx = pd.date_range("2025-07-01", periods=4, freq="MS")
    pol = PiecewiseSharesPolicy([
        {"start": "2025-07-01", "short": 0.2, "nb": 0.7, "tips": 0.1},
        {"start": "2025-09-01", "short": 0.3, "nb": 0.6, "tips": 0.1},
    ])
    df = pol.get(idx)
    assert abs(df.loc[pd.Timestamp("2025-08-01")].sum() - 1.0) < 1e-9
    assert df.loc[pd.Timestamp("2025-07-01"), "short"] == 0.2
    assert df.loc[pd.Timestamp("2025-09-01"), "short"] == 0.3


def test_preview_artifact_created(tmp_path: Path) -> None:
    idx = build_month_index("2025-07-01", 3)
    pol = FixedSharesPolicy(0.2, 0.7, 0.1)
    out = write_issuance_preview(pol, idx, out_path=str(tmp_path / "issuance_preview.csv"))
    assert Path(out).exists()
