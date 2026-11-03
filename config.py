import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Persistent data — Render: mount disk and set DATA_DIR=/var/data
# Default: ./data next to these flat files (survives process restart; use disk for redeploys)
_data = os.getenv("DATA_DIR", str(BASE_DIR / "data"))
DATA_DIR = Path(_data)
DATA_DIR.mkdir(parents=True, exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "9230441788:AAEGUm94Mb4J7bn_kj7kJW6BJpEtErRHz2Q").strip()
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "5427735251").split(",") if x.strip()]
MAX_ACCOUNTS_PER_USER = 15
ADMIN_UNLIMITED = True
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "8080"))
SESSION_FILE = DATA_DIR / "accounts.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
OWNER_HANDLE = "@sjnd88"
