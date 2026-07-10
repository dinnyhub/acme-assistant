import logging
import os
from datetime import datetime

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger that:
    - Creates a new log file each day named acme_YYYY-MM-DD.log
    - Automatically deletes log files older than 7 days
    - Logs to both file and console
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.INFO)

    # Format for all log entries
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Today's log file name — acme_2026-07-09.log
    today = datetime.now().strftime('%Y-%m-%d')
    log_filename = f"logs/acme_{today}.log"

    # File handler — writes to today's file
    file_handler = logging.FileHandler(
        filename=log_filename,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # Console handler — also print to terminal
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Clean up log files older than 7 days
    _cleanup_old_logs()

    return logger

def _cleanup_old_logs():
    """Delete log files older than 7 days."""
    now = datetime.now()
    logs_dir = "logs"

    for filename in os.listdir(logs_dir):
        if filename.startswith("acme_") and filename.endswith(".log"):
            filepath = os.path.join(logs_dir, filename)
            # Get file age in days
            file_age_days = (now - datetime.fromtimestamp(
                os.path.getmtime(filepath)
            )).days
            if file_age_days > 7:
                os.remove(filepath)
                print(f"Deleted old log file: {filename}")