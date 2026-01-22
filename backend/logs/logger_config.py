import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Name of log file
FILENAME = "scraper.log"


# --- Logger Setup Function ---
def init_logger():

    # Create directory if it doesn't exist
    log_dir = Path("backend/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_path = log_dir / FILENAME

    logging.basicConfig(
        handlers=[
            RotatingFileHandler(
                filename=file_path, maxBytes=5 * 1024 * 1024, backupCount=3
            )
        ],
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


# --- Helper Functions ---
def log_header(title: str, width: int = 60):
    separator = "=" * width
    centered_title = title.center(width)
    logging.info("\n%s\n%s\n%s", separator, centered_title, separator)


def log_section(title: str, width: int = 60):
    separator = "-" * width
    centered_title = title.center(width)
    logging.info("\n%s", centered_title)
