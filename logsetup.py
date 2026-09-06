"""Central logging setup — console handler, level from LOG_LEVEL env.

Usage::

    from logsetup import setup_logging
    setup_logging()          # at process start, before anything logs

Levels: INFO (default) shows one line per action; DEBUG adds per-request
detail (every API call, jacket fetch, link lookup).
Third-party libraries (urllib3, PIL, ...) stay at INFO so DEBUG stays readable.
"""

from __future__ import annotations

import logging
import os
import sys

_CONSOLE_FMT = "[%(asctime)s] [%(levelname)8s] %(name)s: %(message)s"

# Modules whose loggers follow LOG_LEVEL; everything else stays at INFO.
_APP_LOG_NAMES = ("tachi", "links", "bot", "render", "b50_render.generate")


def setup_logging(level: str | None = None) -> None:
    """Configure logging once. Explicit *level* beats the LOG_LEVEL env var."""
    root = logging.getLogger()
    if root.handlers:  # already configured by something else
        return
    lvl = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    target = getattr(logging, lvl, logging.INFO)

    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_CONSOLE_FMT))
    root.addHandler(handler)

    for name in _APP_LOG_NAMES:
        logging.getLogger(name).setLevel(target)
