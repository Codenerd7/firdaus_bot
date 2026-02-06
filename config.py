# config.py
import os
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = [int(id) for id in os.getenv("ADMINS", "").split(",") if id]
FUND_GROUP_ID = int(os.getenv("FUND_GROUP_ID", "0"))

# <<< ДОБАВЬ ЭТО >>>
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "database" / "bot_db.sqlite3")
# <<< КОНЕЦ ДОБАВЛЕНИЯ >>>

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
