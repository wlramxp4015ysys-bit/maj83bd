"""
Configuration loader for Telegram Bot and API Backend.
Loads settings from .env file or environment variables with safe defaults.
"""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = BASE_DIR / ".env"
DB_FILE = DATA_DIR / "database.json"
LOG_FILE = DATA_DIR / "operations.log"

# Setup Centralized Logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("A2TV")

def load_env(env_path=ENV_FILE):
    """Simple and robust parser for .env file without external dependencies."""
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val

# Load .env file
load_env()

# Bot Credentials & Settings
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
raw_admin = os.getenv("ADMIN_ID", "0").strip()
try:
    ADMIN_ID = int(raw_admin) if raw_admin else 0
except ValueError:
    ADMIN_ID = 0

# Server Settings
API_HOST = os.getenv("API_HOST", "0.0.0.0").strip()
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8080")))
SECRET_KEY = os.getenv("SECRET_KEY", "goldentv-secret-key-2026").strip()

# Public URL resolution (Railway domain or static public host)
PUBLIC_URL = os.getenv("PUBLIC_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
if PUBLIC_URL:
    if not PUBLIC_URL.startswith("http"):
        PUBLIC_URL = f"https://{PUBLIC_URL}"
else:
    PUBLIC_URL = f"http://{API_HOST}:{API_PORT}"

# App Version Reference (com.A2)
APP_PACKAGE = "com.A2"
CURRENT_APP_VERSION_CODE = 2
CURRENT_APP_VERSION_NAME = "1.1"
