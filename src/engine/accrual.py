from __future__ import annotations

from typing import Dict, Mapping, Optional

import pandas as pd

from .state import DebtState


def compute_interest(
    state: DebtState,
    rates_row: Mapping[str, float],
    *,
    coupon_nb_existing_annual: Optional[float] = None,
    coupon_tips_existing_annual: Optional[float] = None,
) -> Dict[str, float]:
    """
    Compute monthly interest by bucket.

    - Bills: use current short rate.
    - NB: use coupon_nb_existing_annual for existing stock (default to current nb rate).
    - TIPS: use coupon_tips_existing_annual for existing principal (default to current tips rate; CPI accretion=0 for step 10).
    """
    r_short_m = float(rates_row["short"]) / 12.0
    r_nb_m = float((coupon_nb_existing_annual if coupon_nb_existing_annual is not None else rates_row["nb"])) / 12.0
    r_tips_m = float((coupon_tips_existing_annual if coupon_tips_existing_annual is not None else rates_row["tips"])) / 12.0
    i_short = state.stock_short * r_short_m
    i_nb = state.stock_nb * r_nb_m
    i_tips = state.stock_tips * r_tips_m
    return {
        "interest_short": i_short,
        "interest_nb": i_nb,
        "interest_tips": i_tips,
        "interest_total": i_short + i_nb + i_tips,
    }


