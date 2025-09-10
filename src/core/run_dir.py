from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def generate_utc_timestamp() -> str:
    """Return a UTC timestamp in YYYYMMDDTHHMMSSZ format.

    Example: 20250910T143015Z
    """
    now_utc = datetime.now(timezone.utc)
    return now_utc.strftime("%Y%m%dT%H%M%SZ")


def create_run_directory(base_output_dir: str | Path = "output", timestamp: Optional[str] = None) -> Path:
    """Create and return a unique timestamped run directory under base_output_dir.

    The directory name uses a UTC timestamp in the form YYYYMMDDTHHMMSSZ. If a directory
    already exists with that name, numerical suffixes (-1, -2, ...) are appended until a
    unique path is found.

    Parameters
    ----------
    base_output_dir: str | Path
        Base output directory under which the run directory will be created (default: "output").
    timestamp: Optional[str]
        Override the timestamp string (useful for tests). Must be in YYYYMMDDTHHMMSSZ format.

    Returns
    -------
    Path
        The created run directory path.
    """
    base = Path(base_output_dir)
    base.mkdir(parents=True, exist_ok=True)

    ts = timestamp or generate_utc_timestamp()
    candidate = base / ts
    if not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    suffix = 1
    while True:
        alt = base / f"{ts}-{suffix}"
        if not alt.exists():
            alt.mkdir(parents=True, exist_ok=False)
            return alt
        suffix += 1


