from __future__ import annotations

from pathlib import Path

import pandas as pd

from calibration.matrix import (
    INTEREST_CATEGORY_KEEP,
    build_cy_totals,
    build_fy_totals,
    build_monthly_by_category,
    load_interest_raw,
)


def make_sample_df() -> pd.DataFrame:
    data = [
        # Kept
        ["2025-07-31", INTEREST_CATEGORY_KEEP, "ACCRUED INTEREST EXPENSE", "Treasury Notes", 100.0],
        ["2025-07-31", INTEREST_CATEGORY_KEEP, "ACCRUED INTEREST EXPENSE", "Treasury Bills", 50.0],
        ["2025-08-31", INTEREST_CATEGORY_KEEP, "ACCRUED INTEREST EXPENSE", "Inflation Protected Securities (TIPS)", 30.0],
        # Dropped (GAS)
        ["2025-07-31", "GAS TRANSFER", "INTRA-GOVT", "GAS", 999.0],
    ]
    cols = [
        "Record Date",
        "Expense Category Description",
        "Expense Group Description",
        "Expense Type Description",
        "Current Month Expense Amount",
    ]
    return pd.DataFrame(data, columns=cols)


def test_filter_and_columns_and_categories(tmp_path: Path) -> None:
    df = make_sample_df()
    csv = tmp_path / "sample.csv"
    df.to_csv(csv, index=False)
    raw = load_interest_raw(csv)
    assert set(["Record Date", "Calendar Year", "Fiscal Year", "Month", "Debt Category", "Interest Expense"]).issubset(raw.columns)
    # dropped GAS row
    assert (raw["Interest Expense"] > 900).sum() == 0
    # category set
    assert set(raw["Debt Category"]).issubset({"SHORT", "NB", "TIPS", "OTHER"})


def test_fy_cy_totals_match_monthly_sum(tmp_path: Path) -> None:
    df = make_sample_df()
    csv = tmp_path / "sample.csv"
    df.to_csv(csv, index=False)
    raw = load_interest_raw(csv)
    monthly = build_monthly_by_category(raw)
    fy = build_fy_totals(monthly)
    cy = build_cy_totals(monthly)
    assert fy["Interest Expense"].sum() == monthly["Interest Expense"].sum()
    assert cy["Interest Expense"].sum() == monthly["Interest Expense"].sum()
