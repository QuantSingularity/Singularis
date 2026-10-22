from __future__ import annotations

import logging
import os
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOGGER_NAME = "singularis"


def setup_logging(
    log_dir: Path | str | None = None, level: int = logging.INFO
) -> logging.Logger:
    """Log to the console and to <log_dir>/singularis.log."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    directory = Path(log_dir or os.environ.get("SINGULARIS_LOG_DIR") or DEFAULT_LOG_DIR)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(directory / "singularis.log")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except OSError:
        logger.warning("file logging disabled: cannot write to %s", directory)
    return logger
