from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Tuple

import math
import pandas as pd


REQUIRED_RATE_COLS: Tuple[str, str, str] = ("short", "nb", "tips")


def _assert_required_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_RATE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Rates table missing required columns: {missing}")


def _assert_finite(df: pd.DataFrame) -> None:
    if not pd.api.types.is_float_dtype(df["short"]) or not pd.api.types.is_float_dtype(df["nb"]) or not pd.api.types.is_float_dtype(df["tips"]):
        # Coerce and check
        df["short"] = pd.to_numeric(df["short"], errors="coerce")
        df["nb"] = pd.to_numeric(df["nb"], errors="coerce")
        df["tips"] = pd.to_numeric(df["tips"], errors="coerce")
    cols = list(REQUIRED_RATE_COLS)
    if not df[cols].to_numpy().size:
        return
    if not pd.isfinite(df[cols].to_numpy()).all():
        raise ValueError("Rates contain non-finite values (NaN/Inf)")


def build_month_index(anchor_date, horizon_months: int) -> pd.DatetimeIndex:
    ts = pd.Timestamp(anchor_date)
    start = pd.Timestamp(year=ts.year, month=ts.month, day=1)
    return pd.date_range(start=start, periods=horizon_months, freq="MS")


@dataclass(frozen=True)
class ConstantRatesProvider:
    """Deterministic constant rates provider for tests and golden runs.

    Rates are annualized decimals for columns: short, nb, tips.
    """

    values: Mapping[str, float]

    def get(self, index: Iterable[pd.Timestamp]) -> pd.DataFrame:
        idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()
        data = {col: float(self.values[col]) for col in REQUIRED_RATE_COLS}
        for name, v in data.items():
            if not (math.isfinite(v)):
                raise ValueError(f"rate {name} not finite: {v}")
        df = pd.DataFrame({c: [data[c]] * len(idx) for c in REQUIRED_RATE_COLS}, index=idx)
        df.index.name = "date"
        return df


@dataclass
class MonthlyCSVRateProvider:
    """Monthly rates from a CSV with columns: date, short, nb, tips.

    - Validates coverage for any requested monthly index (MS aligned)
    - Ensures values are finite
    """

    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.path.exists():
            raise FileNotFoundError(f"Rates CSV not found: {self.path}")
        df = pd.read_csv(self.path)
        if "date" not in df.columns:
            raise ValueError("Rates CSV must include a 'date' column")
        _assert_required_columns(df)
        df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
        df = df.sort_values("date").reset_index(drop=True)
        # Validate monotonicity
        if not df["date"].is_monotonic_increasing:
            raise ValueError("Rates CSV dates must be monotonically increasing")
        df = df.set_index("date")
        _assert_finite(df)
        self._df = df[REQUIRED_RATE_COLS].copy()

    def get(self, index: Iterable[pd.Timestamp]) -> pd.DataFrame:
        idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()
        missing = idx.difference(self._df.index)
        if len(missing) > 0:
            raise ValueError(f"Rates CSV does not cover requested months: {missing.min()}..{missing.max()}")
        df = self._df.loc[idx]
        df.index.name = "date"
        _assert_finite(df)
        return df


def write_rates_preview(provider, index: Iterable[pd.Timestamp], out_path: str = "output/diagnostics/rates_preview.csv") -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = provider.get(index)
    df.to_csv(out, index=True)
    return out


