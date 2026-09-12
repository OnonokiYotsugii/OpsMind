import logging

from opsmind.core.config import Settings
from opsmind.core.logging import configure_logging


def test_reconfiguration_does_not_duplicate_events_or_change_root(capsys):
    root_handlers = list(logging.getLogger().handlers)
    settings = Settings(_env_file=None, log_level="INFO")
    try:
        configure_logging(settings)
        logger = configure_logging(settings)
        logger.debug("hidden-debug-event")
        logger.info("startup-ready")
        output = capsys.readouterr().err
        assert output.count("startup-ready") == 1
        assert "hidden-debug-event" not in output
        assert "Z INFO opsmind" in output
        assert logging.getLogger().handlers == root_handlers
    finally:
        logger = logging.getLogger("opsmind")
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
