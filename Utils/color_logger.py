import logging
import sys

# ANSI escape codes for colors
LOG_COLORS = {
    'DEBUG': '\033[94m',     # Blue
    'INFO': '\033[92m',      # Green
    'WARNING': '\033[93m',   # Yellow
    'ERROR': '\033[91m',     # Red
    'CRITICAL': '\033[95m',  # Magenta
    'RESET': '\033[0m',      # Reset
}

class ColorFormatter(logging.Formatter):
    def format(self, record):
        log_color = LOG_COLORS.get(record.levelname, LOG_COLORS['RESET'])
        reset = LOG_COLORS['RESET']
        message = super().format(record)
        return f"{log_color}{message}{reset}"


def get_logger(name=__name__):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = ColorFormatter('[%(levelname)s] %(asctime)s - %(name)s: %(message)s', "%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger
