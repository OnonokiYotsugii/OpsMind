"""Application-owned logging; call explicitly at process startup."""

import logging
import time

from opsmind.core.config import Settings


def configure_logging(settings: Settings) -> logging.Logger:
    """Configure only the opsmind logger, preserving third-party/root handlers.

    Log event descriptions, never credentials, configuration dumps or raw payloads.
    SecretStr protects accidental repr/serialization; it is not a log scrubber.
    """
    logger = logging.getLogger("opsmind")
    logger.setLevel(settings.log_level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
