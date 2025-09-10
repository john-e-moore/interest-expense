from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Tuple

import pandas as pd

from macro.rates import build_month_index
from macro.issuance import FixedSharesPolicy
from .state import DebtState
from .accrual import compute_interest
from .transitions import update_state, compute_redemptions


@dataclass
class ProjectionEngine:
    rates_provider: object  # expects .get(index)->DataFrame columns short, nb, tips
    issuance_policy: FixedSharesPolicy

    def run(
        self,
        index: Iterable[pd.Timestamp],
        start_state: DebtState,
        deficits_monthly: pd.Series,
        other_interest_monthly: pd.Series | None = None,
        *,
        decay_nb: float = 0.01,
        decay_tips: float = 0.01,
        coupon_nb_existing_annual: float | None = None,
        coupon_tips_existing_annual: float | None = None,
    ) -> pd.DataFrame:
        idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()
        rates = self.rates_provider.get(idx)
        shares = self.issuance_policy.get(idx)
        deficits = deficits_monthly.reindex(idx).fillna(0.0)
        other = (other_interest_monthly.reindex(idx).fillna(0.0)) if other_interest_monthly is not None else pd.Series(0.0, index=idx)

        rows = []
        state = start_state
        for dt in idx:
            r_row = rates.loc[dt]
            sh_row = shares.loc[dt]
            # Compute interest
            acc = compute_interest(
                state,
                r_row,
                coupon_nb_existing_annual=coupon_nb_existing_annual,
                coupon_tips_existing_annual=coupon_tips_existing_annual,
            )
            # Redemptions
            red_short, red_nb, red_tips = compute_redemptions(state, decay_nb, decay_tips)
            red_total = red_short + red_nb + red_tips
            # Budget identity: GFN = primary_deficit + interest + redemptions
            gfn = float(deficits.loc[dt]) + acc["interest_total"] + float(other.loc[dt]) + red_total
            new_short = float(sh_row["short"]) * gfn
            new_nb = float(sh_row["nb"]) * gfn
            new_tips = float(sh_row["tips"]) * gfn

            rows.append(
                {
                    "date": dt,
                    "stock_short": state.stock_short,
                    "stock_nb": state.stock_nb,
                    "stock_tips": state.stock_tips,
                    **acc,
                    "other_interest": float(other.loc[dt]),
                    "shares_short": float(sh_row["short"]),
                    "shares_nb": float(sh_row["nb"]),
                    "shares_tips": float(sh_row["tips"]),
                    "gfn": gfn,
                    "redemptions_short": red_short,
                    "redemptions_nb": red_nb,
                    "redemptions_tips": red_tips,
                    "redemptions_total": red_total,
                }
            )

            # State update with redemptions/decay
            state = update_state(state, new_short, new_nb, new_tips, decay_nb=decay_nb, decay_tips=decay_tips)

        df = pd.DataFrame(rows).set_index("date")
        out = Path("output/diagnostics/monthly_trace.parquet")
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            df.to_parquet(out)
        except Exception:
            # Fallback to CSV if parquet deps missing
            df.to_csv(out.with_suffix(".csv"))
        return df


