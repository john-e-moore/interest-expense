from __future__ import annotations

from datetime import date

import pandas as pd

from core.dates import fiscal_year, fiscal_year_series, write_sample_fy_check


def test_boundary_sept_30_and_oct_1() -> None:
    assert fiscal_year(date(2025, 9, 30)) == 2025
    assert fiscal_year(date(2025, 10, 1)) == 2026


def test_vectorized_mapping_consistency() -> None:
    dates = pd.to_datetime(["2024-09-30", "2024-10-01", "2025-09-30", "2025-10-01"])
    fy = fiscal_year_series(dates)
    assert fy.tolist() == [2024, 2025, 2025, 2026]


def test_sample_artifact_written(tmp_path) -> None:
    out = write_sample_fy_check(tmp_path / "sample.csv")
    df = pd.read_csv(out)
    assert len(df) == 10
    assert {"date", "fy"}.issubset(df.columns)


