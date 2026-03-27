"""Logging system with file output, terminal debug, and auto-cleanup."""

import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.core.config import BASE_DIR

LOG_DIR = BASE_DIR / "logs"
LOG_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)-5s] %(name)-12s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _add_stream_handler(root: logging.Logger, level: int, formatter: logging.Formatter) -> None:
    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(formatter)
    root.addHandler(sh)


def setup_logging(
    debug: bool = False,
    log_level: str = "INFO",
    retention_days: int = 7,
) -> None:
    root = logging.getLogger("ykt")

    # Already configured — avoid duplicate handlers on repeated calls
    if root.handlers:
        return

    level = logging.DEBUG if debug else getattr(logging, log_level.upper(), logging.INFO)
    root.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[ykt-cli] 警告: 无法创建日志目录 {LOG_DIR}: {e}，文件日志已禁用", file=sys.stderr)
        _add_stream_handler(root, level, formatter)
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = LOG_DIR / f"{timestamp}.log"

    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
    except OSError as e:
        print(f"[ykt-cli] 警告: 无法创建日志文件 {log_file}: {e}，文件日志已禁用", file=sys.stderr)
        _add_stream_handler(root, level, formatter)
        return
    fh.setLevel(level)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    if debug:
        _add_stream_handler(root, logging.DEBUG, formatter)

    _cleanup_old_logs(retention_days)


def get_logger(name: str) -> logging.Logger:
    module_name = name.split(".")[-1]
    return logging.getLogger(f"ykt.{module_name}")


def _cleanup_old_logs(days: int) -> None:
    if not LOG_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=days)
    for log_file in LOG_DIR.glob("*.log"):
        try:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                log_file.unlink()
        except OSError:
            pass  # Best-effort cleanup — don't crash on permission errors
