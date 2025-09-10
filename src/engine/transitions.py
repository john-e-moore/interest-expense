from __future__ import annotations

from .state import DebtState


def compute_redemptions(state: DebtState, decay_nb: float, decay_tips: float) -> tuple[float, float, float]:
    """
    Monthly redemptions by bucket using simple rules:
      - Bills: full rollover (redeem 100% of bills outstanding)
      - NB/TIPS: constant decay rates (fractions 0..1) per month
    """
    r_short = state.stock_short  # full redemption of bills each month
    r_nb = state.stock_nb * float(decay_nb)
    r_tips = state.stock_tips * float(decay_tips)
    return float(r_short), float(r_nb), float(r_tips)


def update_state(
    state: DebtState,
    new_short: float,
    new_nb: float,
    new_tips: float,
    decay_nb: float,
    decay_tips: float,
) -> DebtState:
    """
    Apply redemptions and add new issuance.
    """
    r_short, r_nb, r_tips = compute_redemptions(state, decay_nb, decay_tips)
    return DebtState(
        stock_short=state.stock_short - r_short + float(new_short),
        stock_nb=state.stock_nb - r_nb + float(new_nb),
        stock_tips=state.stock_tips - r_tips + float(new_tips),
    )


