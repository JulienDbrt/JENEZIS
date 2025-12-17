"""Centralized, structured JSON logging setup."""

import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logging():
    """
    Configures logging to output structured JSON logs.
    This should be called once at application startup.
    """
    log_level = logging.INFO
    
    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Remove any existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create a handler that outputs to stdout
    log_handler = logging.StreamHandler(sys.stdout)
    
    # Use a custom format for the JSON logs
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(module)s %(funcName)s %(lineno)d %(message)s"
    )
    
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)

    # Suppress verbose logs from some libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.WARNING)

    # Example of how to use it:
    # import logging
    # logger = logging.getLogger(__name__)
    # logger.info("This is an info message", extra={'task_id': '123', 'cost': 0.05})
