"""
"""

from pathlib import Path

# Base directory for SQLite storage
BASE_DIR = Path(__file__).resolve().parent

# Default to SQLite if the user doesn't configure a database
DATABASE_URL_ASYNC = f"sqlite+aiosqlite:///{BASE_DIR}/db.sqlite3"
DATABASE_URL_SYNC = f"sqlite:///{BASE_DIR}/db.sqlite3"

# Other default settings
DEBUG = True
SECRET_KEY = "default-secret-key"
