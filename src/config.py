import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Centralized project configuration and shared logger.
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "api.log"

load_dotenv(BASE_DIR / ".env")

ADOBE_ACCOUNTS_FILE = Path(
    os.getenv("ADOBE_ACCOUNTS_FILE", str(BASE_DIR / "adobe_accounts.json"))
)

# Adobe monthly quota.
MAX_ADOBE_CREDITS = int(os.getenv("MAX_ADOBE_CREDITS", "500"))

# Dashboard access token used to protect the web admin UI.
DASHBOARD_ACCESS_TOKEN = os.getenv(
    "DASHBOARD_ACCESS_TOKEN",
    os.getenv("DASHBOARD_TOKEN", ""),
)

LOG_DIR.mkdir(exist_ok=True)
ENABLE_COLOR = sys.stderr.isatty() and not os.getenv("NO_COLOR")

class PrettyFormatter(logging.Formatter):
    _colors = {
        logging.DEBUG: "\033[38;5;244m",
        logging.INFO: "\033[38;5;39m",
        logging.WARNING: "\033[38;5;214m",
        logging.ERROR: "\033[38;5;196m",
        logging.CRITICAL: "\033[1;38;5;196m",
    }
    _reset = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%H:%M:%S")
        level = f"{record.levelname:<8}"
        module = f"{record.name:<22}"
        message = super().format(record)
        color = self._colors.get(record.levelno, "")

        line = f"{timestamp}  {level}  {module}  {message}"
        if color and ENABLE_COLOR:
            return f"{color}{line}{self._reset}"
        return line


class CompactFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level = f"{record.levelname:<8}"
        module = f"{record.name:<22}"
        message = super().format(record)
        return f"{timestamp} | {level} | {module} | {message}"


console_handler = logging.StreamHandler()
console_handler.setFormatter(PrettyFormatter("%(message)s"))

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(CompactFormatter("%(message)s"))

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    handlers=[console_handler, file_handler],
)

logger = logging.getLogger("pdf-compression-api")
