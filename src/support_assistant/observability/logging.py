import json
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger("aegis")


def configure_logging():
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def event(name, **fields):
    # Callers supply only operational identifiers, categories and timings.
    # Never add raw customer text, headers, tokens or internal prompts here.
    logger.info(
        json.dumps(
            {"time": datetime.now(timezone.utc).isoformat(), "event": name, **fields},
            default=str,
        )
    )
