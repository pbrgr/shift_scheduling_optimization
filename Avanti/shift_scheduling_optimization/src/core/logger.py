import logging
from datetime import datetime
import os
import sys

def setup_logging(base_output_path: str) -> logging.Logger:
    logs_dir = os.path.join(base_output_path, "logs")
    os.makedirs(logs_dir, exist_ok=True)
   # logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f"run_{timestamp}.log")

    logger = logging.getLogger("shift_scheduler")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Clear handlers in case this file is run repeatedly in the same interpreter
    if logger.handlers:
        logger.handlers.clear()

    formatter_obj = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter_obj)

    #WIS BEGIN
    #console_handler = logging.StreamHandler(sys.stdout)
    console_handler = logging.StreamHandler(sys.stderr)
    #WIS END
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter_obj)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("Logging initialized")
    logger.info("Log file: %s", log_file)

    return logger