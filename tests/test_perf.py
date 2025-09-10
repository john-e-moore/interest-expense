from __future__ import annotations

import json
from pathlib import Path

from diagnostics.perf import run_perf_profile


def test_perf_profile_runs_quickly() -> None:
    p = run_perf_profile()
    data = json.loads(Path(p).read_text())
    # Simple asserts: file present, months positive, seconds finite
    assert data["months"] > 0
    assert data["rows"] == data["months"]
    assert data["seconds"] >= 0.0


