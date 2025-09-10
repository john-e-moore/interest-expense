from __future__ import annotations

from pathlib import Path

from core.logging_utils import setup_run_logger, log_run_start, log_run_end


def test_setup_and_write_log(tmp_path: Path) -> None:
    log_path = tmp_path / "run_forward.log"
    logger = setup_run_logger(log_path=log_path, debug=False)
    log_run_start(logger, run_dir=tmp_path, config_path="input/macro.yaml", git_sha="abc123")
    log_run_end(logger, status="success")

    assert log_path.exists()
    text = log_path.read_text(encoding="utf-8")
    assert "RUN START" in text
    assert "RUN END" in text


