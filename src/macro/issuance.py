from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Tuple

import math
import pandas as pd


# Issuance covers marketable buckets only; OTHER is excluded (exogenous)
REQUIRED_SHARE_COLS: Tuple[str, str, str] = ("short", "nb", "tips")


def _validate_shares_dict(values: Mapping[str, float]) -> Tuple[float, float, float]:
    missing = [c for c in REQUIRED_SHARE_COLS if c not in values]
    if missing:
        raise ValueError(f"Missing share keys: {missing}")
    s = float(values["short"])  # type: ignore[arg-type]
    n = float(values["nb"])  # type: ignore[arg-type]
    t = float(values["tips"])  # type: ignore[arg-type]
    for name, v in ("short", s), ("nb", n), ("tips", t):
        if not (0.0 <= v <= 1.0) or not math.isfinite(v):
            raise ValueError(f"share {name} out of bounds or non-finite: {v}")
    total = s + n + t
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"shares must sum to 1.0 (±1e-6), got {total}")
    return s, n, t


@dataclass(frozen=True)
class FixedSharesPolicy:
    """Constant issuance shares across the horizon.

    Shares are decimals in [0,1] for SHORT, NB, TIPS and must sum≈1.
    """

    short: float
    nb: float
    tips: float

    def __post_init__(self) -> None:  # type: ignore[override]
        _validate_shares_dict({"short": self.short, "nb": self.nb, "tips": self.tips})

    def get(self, index: Iterable[pd.Timestamp]) -> pd.DataFrame:
        idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()
        df = pd.DataFrame(
            {
                "short": [self.short] * len(idx),
                "nb": [self.nb] * len(idx),
                "tips": [self.tips] * len(idx),
            },
            index=idx,
        )
        df.index.name = "date"
        return df


@dataclass
class PiecewiseSharesPolicy:
    """Piecewise-constant shares switching at monthly start dates.

    segments: list of mappings with keys {start, short, nb, tips}
    """

    segments: List[Mapping[str, float]]

    def __post_init__(self) -> None:
        norm_segments: List[Tuple[pd.Timestamp, Tuple[float, float, float]]] = []
        for seg in self.segments:
            if "start" not in seg:
                raise ValueError("segment requires 'start' key")
            start = pd.Timestamp(seg["start"]).to_period("M").to_timestamp()
            snt = _validate_shares_dict(seg)  # type: ignore[arg-type]
            norm_segments.append((start, snt))
        # sort and dedupe by start
        norm_segments.sort(key=lambda x: x[0])
        self._segments = norm_segments

    def get(self, index: Iterable[pd.Timestamp]) -> pd.DataFrame:
        idx = pd.to_datetime(pd.DatetimeIndex(index)).to_period("M").to_timestamp()
        # For each date, pick last segment whose start <= date
        starts = [s for s, _ in self._segments]
        values = [v for _, v in self._segments]
        out = []
        for d in idx:
            pick = None
            for s, v in zip(starts, values):
                if s <= d:
                    pick = v
                else:
                    break
            if pick is None:
                # Before first segment: use first
                pick = values[0]
            out.append(pick)
        df = pd.DataFrame(out, columns=["short", "nb", "tips"], index=idx)
        df.index.name = "date"
        return df


def write_issuance_preview(provider, index: Iterable[pd.Timestamp], out_path: str = "output/diagnostics/issuance_preview.csv") -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = provider.get(index)
    df.to_csv(out, index=True)
    return out


