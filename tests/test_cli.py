from __future__ import annotations

import subprocess


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


