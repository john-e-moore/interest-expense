from __future__ import annotations

from pathlib import Path

import pandas as pd

from macro.gdp import GDPModel, build_gdp_function, write_gdp_check_csv


def test_anchor_equality() -> None:
    model = build_gdp_function("2025-07-01", 300.0, {2026: 0.04, 2025: 0.03})
    # fiscal_year('2025-07-01') = FY2025
    assert abs(model.gdp_fy(2025) - 300.0) < 1e-9


def test_compounding_forward_and_backward() -> None:
    model = build_gdp_function("2025-07-01", 100.0, {2026: 0.10, 2027: 0.05, 2025: 0.08})
    # Forward: 2026 = 100 * 1.10
    assert abs(model.gdp_fy(2026) - 110.0) < 1e-9
    # Backward: 2024 = 100 / 1.08
    assert abs(model.gdp_fy(2024) - (100.0 / 1.08)) < 1e-9


def test_cy_mapping_simple_average() -> None:
    model = build_gdp_function("2025-07-01", 100.0, {2026: 0.20, 2025: 0.10})
    # FY2025 = 100; FY2026 = 120
    # CY2025 = 0.75*FY2025 + 0.25*FY2026 = 0.75*100 + 0.25*120 = 105
    assert abs(model.gdp_cy(2025) - 105.0) < 1e-9


def test_artifact_written(tmp_path: Path) -> None:
    model = build_gdp_function("2025-07-01", 100.0, {2026: 0.10, 2025: 0.05})
    out = write_gdp_check_csv(model, years=[2024, 2025, 2026], out_path=str(tmp_path / "gdp_check.csv"))
    df = pd.read_csv(out)
    assert df.shape[0] == 3
    assert {"year", "gdp_fy", "gdp_cy"}.issubset(df.columns)
