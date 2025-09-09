from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Union

import pandas as pd


DateLike = Union[date, datetime, pd.Timestamp]


def fiscal_year(ts: DateLike) -> int:
    """Return US Federal Fiscal Year for a given timestamp.

    Fiscal year runs Oct 1 → Sep 30. Example: 2025-10-01 is FY 2026.
    """
    if isinstance(ts, pd.Timestamp):
        year = ts.year
        month = ts.month
    elif isinstance(ts, datetime):
        year = ts.year
        month = ts.month
    elif isinstance(ts, date):
        year = ts.year
        month = ts.month
    else:
        # Allow strings via pandas parsing for convenience
        t = pd.Timestamp(ts)  # type: ignore[arg-type]
        year = t.year
        month = t.month
    return year + 1 if month >= 10 else year


def fiscal_year_series(values: Union[pd.Series, pd.DatetimeIndex, Iterable[DateLike]]) -> pd.Series:
    """Vectorized fiscal year mapping for a collection of datelike values.

    Returns an int64 pandas Series aligned with the input order.
    """
    if isinstance(values, pd.Series):
        idx = values.index
        ts = pd.to_datetime(values)
        fy = ts.dt.year + (ts.dt.month >= 10).astype(int)
        return pd.Series(fy.astype("int64").to_numpy(), index=idx, name="fy")
    elif isinstance(values, pd.DatetimeIndex):
        idx = values
        ts = values
        fy_vals = ts.year + (ts.month >= 10).astype(int)
        return pd.Series(pd.Index(fy_vals).astype("int64"), index=idx, name="fy")
    else:
        ts = pd.to_datetime(pd.Series(list(values)))
        idx = ts.index
        fy = ts.dt.year + (ts.dt.month >= 10).astype(int)
        return pd.Series(fy.astype("int64").to_numpy(), index=idx, name="fy")


def write_sample_fy_check(out_path: Union[str, Path] = "output/diagnostics/sample_fy_check.csv") -> Path:
    """Write a 10-row CSV demonstrating fiscal year mapping across the boundary.

    Uses dates around Sep→Oct boundary for a recent year.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2025-09-27", "2025-10-06", freq="D")
    df = pd.DataFrame({"date": dates, "fy": fiscal_year_series(dates).to_numpy()})
    df.to_csv(out, index=False)
    return out


