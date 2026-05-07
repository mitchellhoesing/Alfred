"""Logging configuration. Idempotent — safe to call from multiple entry points."""

from __future__ import annotations

import logging
import sys


_HANDLER_NAME = "alfred_stderr"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(h.get_name() == _HANDLER_NAME for h in root.handlers):
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
