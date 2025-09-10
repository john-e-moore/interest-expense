from __future__ import annotations

import pandas as pd

from macro.rates import build_month_index, ConstantRatesProvider
from macro.issuance import FixedSharesPolicy
from engine.state import DebtState
from engine.project import ProjectionEngine


def test_budget_identity_simple() -> None:
    idx = build_month_index("2025-07-01", 2)
    rates = ConstantRatesProvider({"short": 0.03, "nb": 0.04, "tips": 0.02})
    issuance = FixedSharesPolicy(short=0.3, nb=0.6, tips=0.1)
    start = DebtState(stock_short=1_000_000.0, stock_nb=500_000.0, stock_tips=200_000.0)
    deficits = pd.Series(123.0, index=idx)  # small constant primary deficit

    engine = ProjectionEngine(rates_provider=rates, issuance_policy=issuance)
    df = engine.run(idx, start, deficits, decay_nb=0.01, decay_tips=0.01)

    # Identity per month: GFN = deficit + interest + redemptions
    lhs = df["gfn"]
    rhs = df["interest_total"] + deficits + df["redemptions_total"]
    assert (abs(lhs - rhs) < 1e-6).all()


