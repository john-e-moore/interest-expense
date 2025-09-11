from __future__ import annotations

import subprocess
from pathlib import Path


def test_cli_dry_run() -> None:
    # Ensure the CLI parses and exits without running
    res = subprocess.run([
        "venv/bin/python",
        "scripts/run_forward.py",
        "--config",
        "input/macro.yaml",
        "--dry-run",
    ], capture_output=True, text=True)
    assert res.returncode == 0
    assert "DRY RUN OK" in res.stdout


def test_cli_debug_logs(tmp_path: Path) -> None:
    # Run a minimal diagnostics pass with debug and custom outdir
    out = tmp_path / "output"
    res = subprocess.run([
        "venv/bin/python",
        "scripts/run_forward.py",
        "--config",
        "input/macro.yaml",
        "--diagnostics",
        "--debug",
        "--golden",
        "--outdir",
        str(out),
    ], capture_output=True, text=True)
    assert res.returncode == 0
    # Find the run directory created under out
    runs = sorted(list(out.iterdir()))
    assert runs, "no run directory created"
    log = runs[-1] / "run_forward.log"
    assert log.exists()
    text = log.read_text(encoding="utf-8")
    # Check for key markers per T6b
    assert "RUN START" in text
    assert "RATES PREVIEW" in text
    assert "ISSUANCE PREVIEW" in text
    assert "ENGINE START" in text
    assert "ENGINE END" in text
    assert "ANNUALIZE DONE" in text
    assert "QA" in text or "QA WRITE" in text
    assert "RUN END" in text


