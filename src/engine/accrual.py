from __future__ import annotations

from typing import Dict, Mapping

import pandas as pd

from .state import DebtState


def compute_interest(state: DebtState, rates_row: Mapping[str, float]) -> Dict[str, float]:
    """
    Compute monthly interest by bucket using annualized rates (divide by 12).
    """
    r_short = float(rates_row["short"]) / 12.0
    r_nb = float(rates_row["nb"]) / 12.0
    r_tips = float(rates_row["tips"]) / 12.0
    i_short = state.stock_short * r_short
    i_nb = state.stock_nb * r_nb
    i_tips = state.stock_tips * r_tips
    return {
        "interest_short": i_short,
        "interest_nb": i_nb,
        "interest_tips": i_tips,
        "interest_total": i_short + i_nb + i_tips,
    }


