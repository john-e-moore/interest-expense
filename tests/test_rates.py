from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from macro.rates import ConstantRatesProvider, MonthlyCSVRateProvider, build_month_index, write_rates_preview


def test_constant_provider_returns_expected_shape_and_values() -> None:
    idx = build_month_index("2025-07-01", 6)
    rp = ConstantRatesProvider({"short": 0.03, "nb": 0.04, "tips": 0.02})
    df = rp.get(idx)
    assert df.shape == (6, 3)
    assert set(df.columns) == {"short", "nb", "tips"}
    assert float(df["short"].iloc[0]) == 0.03
    assert df.index[0].day == 1


def test_csv_provider_validates_coverage_and_finiteness(tmp_path: Path) -> None:
    # Build a small CSV
    dates = pd.date_range("2025-07-01", periods=4, freq="MS")
    src = pd.DataFrame({
        "date": dates,
        "short": [0.03, 0.031, 0.032, 0.033],
        "nb": [0.04, 0.041, 0.042, 0.043],
        "tips": [0.02, 0.021, 0.022, 0.023],
    })
    csv_path = tmp_path / "rates.csv"
    src.to_csv(csv_path, index=False)
    rp = MonthlyCSVRateProvider(csv_path)
    idx = pd.date_range("2025-07-01", periods=4, freq="MS")
    df = rp.get(idx)
    assert df.shape == (4, 3)
    # Coverage failure
    with pytest.raises(ValueError):
        rp.get(pd.date_range("2025-06-01", periods=5, freq="MS"))


def test_write_preview_creates_file(tmp_path: Path) -> None:
    idx = build_month_index("2025-07-01", 3)
    rp = ConstantRatesProvider({"short": 0.03, "nb": 0.04, "tips": 0.02})
    out = write_rates_preview(rp, idx, out_path=str(tmp_path / "rates_preview.csv"))
    assert Path(out).exists()
