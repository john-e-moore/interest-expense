from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import pandas as pd

from core.dates import fiscal_year


@dataclass(frozen=True)
class GDPModel:
    """Annual GDP callables for Fiscal Year (FY) and Calendar Year (CY).

    Growth rates are specified as decimal y/y growth by fiscal year, e.g.,
    growth_fy[2026] = 0.04 means FY2026 level = FY2025 level * (1 + 0.04).
    """

    anchor_fy: int
    anchor_value_usd_millions: float
    growth_fy: Dict[int, float]

    def gdp_fy(self, year: int) -> float:
        if year == self.anchor_fy:
            return float(self.anchor_value_usd_millions)
        level = float(self.anchor_value_usd_millions)
        if year > self.anchor_fy:
            # Multiply forward
            for y in range(self.anchor_fy + 1, year + 1):
                if y not in self.growth_fy:
                    raise KeyError(f"Missing growth rate for FY{y}")
                level *= 1.0 + float(self.growth_fy[y])
            return level
        # Divide backward
        for y in range(self.anchor_fy, year, -1):
            if y not in self.growth_fy:
                raise KeyError(f"Missing growth rate for FY{y}")
            level /= 1.0 + float(self.growth_fy[y])
        return level

    def gdp_cy(self, year: int) -> float:
        """Approximate CY level using a 9/3 month split of FY levels.

        CY(Y) = 0.75 * FY(Y) + 0.25 * FY(Y+1)
        """
        return 0.75 * self.gdp_fy(year) + 0.25 * self.gdp_fy(year + 1)


def build_gdp_function(anchor_date, anchor_gdp: float, growth_fy: Dict[int, float]) -> GDPModel:
    anchor_fy = fiscal_year(pd.Timestamp(anchor_date))
    return GDPModel(
        anchor_fy=anchor_fy,
        anchor_value_usd_millions=float(anchor_gdp),
        growth_fy={int(k): float(v) for k, v in growth_fy.items()},
    )


def write_gdp_check_csv(
    model: GDPModel,
    years: Optional[Iterable[int]] = None,
    out_path: str = "output/diagnostics/gdp_check.csv",
) -> str:
    if years is None:
        years = list(range(model.anchor_fy - 1, model.anchor_fy + 4))
    df = pd.DataFrame({
        "year": list(years),
    })
    df["gdp_fy"] = df["year"].map(model.gdp_fy)
    # Tolerate missing growth for year+1 by emitting NaN for gdp_cy
    def _safe_cy(y: int) -> float:
        try:
            return float(model.gdp_cy(int(y)))
        except Exception:  # noqa: BLE001
            return float("nan")
    df["gdp_cy"] = df["year"].map(_safe_cy)
    p = pd.Path(out_path) if hasattr(pd, "Path") else out_path  # type: ignore[truthy-bool]
    # Use pathlib for directories
    from pathlib import Path as _P

    out = _P(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return str(out)


