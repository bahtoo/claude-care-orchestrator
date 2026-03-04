"""
Structured audit logging for HIPAA compliance trail.

Every PHI detection, redaction, and FHIR generation event is logged
with structured JSON for auditability.
"""

import logging
import sys
from pathlib import Path

from care_orchestrator.config import settings


def setup_logging() -> logging.Logger:
    """Configure and return the application logger with both file and console handlers."""
    logger = logging.getLogger("care_orchestrator")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Prevent duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt='{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
        '"module": "%(module)s", "message": "%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (create directory if needed)
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Module-level logger instance
logger = setup_logging()
