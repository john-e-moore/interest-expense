from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def get_git_sha() -> Optional[str]:
    """Return the current git commit SHA, if available; otherwise None."""
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        return sha or None
    except Exception:
        return None


def setup_run_logger(log_path: Path, debug: bool = False) -> logging.Logger:
    """Create or return a process-wide logger writing to log_path.

    Ensures idempotent handler setup to avoid duplicate lines when called repeatedly.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("run")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Avoid duplicate handlers to the same file
    for h in list(logger.handlers):
        if isinstance(h, logging.FileHandler):
            try:
                if Path(h.baseFilename) == log_path:
                    return logger
            except Exception:
                continue

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def log_run_start(logger: logging.Logger, run_dir: Path, config_path: Path | str, git_sha: Optional[str]) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    logger.info("RUN START utc=%s run_dir=%s config=%s git_sha=%s", ts, str(run_dir), str(config_path), git_sha or "none")


def log_run_end(logger: logging.Logger, status: str = "success") -> None:
    ts = datetime.now(timezone.utc).isoformat()
    logger.info("RUN END utc=%s status=%s", ts, status)


