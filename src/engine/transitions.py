from __future__ import annotations

from .state import DebtState


def update_state(state: DebtState, new_short: float, new_nb: float, new_tips: float) -> DebtState:
    """
    Minimal transition: add new issuance to existing stocks; ignore redemptions for step 9.
    """
    return DebtState(
        stock_short=state.stock_short + float(new_short),
        stock_nb=state.stock_nb + float(new_nb),
        stock_tips=state.stock_tips + float(new_tips),
    )


