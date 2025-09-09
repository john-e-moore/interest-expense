from __future__ import annotations

from pathlib import Path

import pandas as pd

from calibration.stocks import build_outstanding_by_bucket_from_mspd


def _make_sample_csv(tmp_path: Path) -> Path:
    rows = [
        {"Record Date": "2025-06-30", "Security Type Description": "Marketable", "Security Class 1 Description": "Bills Maturity Value", "Outstanding Amount (in Millions)": 100.0},
        {"Record Date": "2025-06-30", "Security Type Description": "Marketable", "Security Class 1 Description": "Notes", "Outstanding Amount (in Millions)": 1000.0},
        {"Record Date": "2025-06-30", "Security Type Description": "Marketable", "Security Class 1 Description": "Inflation-Indexed Securities (TIPS)", "Outstanding Amount (in Millions)": 200.0},
        {"Record Date": "2025-06-30", "Security Type Description": "Non-Marketable", "Security Class 1 Description": "Savings Bonds", "Outstanding Amount (in Millions)": 999.0},
        {"Record Date": "2025-07-31", "Security Type Description": "Marketable", "Security Class 1 Description": "Bills Maturity Value", "Outstanding Amount (in Millions)": 110.0},
        {"Record Date": "2025-07-31", "Security Type Description": "Marketable", "Security Class 1 Description": "Bonds", "Outstanding Amount (in Millions)": 1050.0},
        {"Record Date": "2025-07-31", "Security Type Description": "Marketable", "Security Class 1 Description": "TIPS", "Outstanding Amount (in Millions)": 210.0},
    ]
    df = pd.DataFrame(rows)
    p = tmp_path / "mspd_sample.csv"
    df.to_csv(p, index=False)
    return p


def test_build_outstanding_by_bucket_from_mspd(tmp_path: Path) -> None:
    path = _make_sample_csv(tmp_path)
    out = build_outstanding_by_bucket_from_mspd(path)

    assert list(out.columns) == ["Record Date", "stock_short", "stock_nb", "stock_tips"]
    assert pd.to_datetime(out["Record Date"]).is_monotonic_increasing

    june = out[out["Record Date"] == "2025-06-30"].iloc[0]
    assert june["stock_short"] == 100.0
    assert june["stock_nb"] == 1000.0
    assert june["stock_tips"] == 200.0

    july = out[out["Record Date"] == "2025-07-31"].iloc[0]
    assert july["stock_short"] == 110.0
    assert july["stock_nb"] == 1050.0
    assert july["stock_tips"] == 210.0

    assert (out[["stock_short", "stock_nb", "stock_tips"]] >= 0).all().all()


