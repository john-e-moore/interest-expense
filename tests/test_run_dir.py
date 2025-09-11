from __future__ import annotations

from pathlib import Path
import re

from core.run_dir import create_run_directory


def test_create_run_directory_unique(tmp_path: Path) -> None:
    base = tmp_path / "output"
    # Fixed timestamp for deterministic test
    ts = "20250101T000000Z"
    p1 = create_run_directory(base_output_dir=base, timestamp=ts)
    p2 = create_run_directory(base_output_dir=base, timestamp=ts)

    assert p1.exists() and p1.is_dir()
    assert p2.exists() and p2.is_dir()
    assert p1 != p2
    assert p1.name == ts
    assert p2.name.startswith(ts + "-")


def test_create_run_directory_default(tmp_path: Path) -> None:
    base = tmp_path / "output"
    p = create_run_directory(base_output_dir=base)
    assert p.exists() and p.is_dir()
    # Format check: YYYYMMDDTHHMMSSZ, optionally with -N suffix for uniqueness
    pattern = re.compile(r"^\d{8}T\d{6}Z(?:-\d+)?$")
    assert pattern.match(p.name)


