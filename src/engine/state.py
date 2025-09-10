from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DebtState:
    stock_short: float
    stock_nb: float
    stock_tips: float

    def total(self) -> float:
        return float(self.stock_short + self.stock_nb + self.stock_tips)


