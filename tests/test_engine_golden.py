from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from macro.rates import build_month_index, ConstantRatesProvider
from macro.issuance import FixedSharesPolicy
from engine.state import DebtState
from engine.project import ProjectionEngine


def test_engine_golden_minimal() -> None:
    # 3-month golden run
    idx = build_month_index("2025-07-01", 3)
    rates = ConstantRatesProvider({"short": 0.03, "nb": 0.04, "tips": 0.02})
    issuance = FixedSharesPolicy(short=0.2, nb=0.7, tips=0.1)
    start = DebtState(stock_short=1_000_000.0, stock_nb=2_000_000.0, stock_tips=500_000.0)
    deficits = pd.Series(0.0, index=idx)

    engine = ProjectionEngine(rates_provider=rates, issuance_policy=issuance)
    df = engine.run(idx, start, deficits)

    # Contiguous dates and correct length
    assert len(df) == len(idx)
    assert (pd.DatetimeIndex(df.index) == idx).all()

    # Finite numbers, no NaNs
    assert df.isna().sum().sum() == 0
    for col in ["interest_short", "interest_nb", "interest_tips", "interest_total", "gfn"]:
        assert math.isfinite(float(df[col].iloc[0]))

    # Shares valid
    ssum = df[["shares_short", "shares_nb", "shares_tips"]].sum(axis=1)
    assert (abs(ssum - 1.0) < 1e-9).all()


