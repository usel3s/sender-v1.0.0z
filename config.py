import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "2040"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "b18441a1ff607e10a989891a5462e627")
PRIVATE_CHANNEL_ID = os.getenv("PRIVATE_CHANNEL_ID", "")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'bot.db'}")
SESSIONS_DIR = BASE_DIR / "sessions"

DEFAULT_START_MESSAGE = (
    '<b><tg-emoji emoji-id="6030400221232501136">🤖</tg-emoji> Добро пожаловать!</b>\n\n'
    "Используйте меню ниже для управления рассылкой в личные сообщения."
)
