import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from handlers import user, admin, statistics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")

# Global bot instance (imported by handlers)
bot: Bot = None  # type: ignore


async def main():
    global bot

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env файле!")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register routers — order matters: admin first to not intercept /start etc.
    dp.include_router(admin.router)
    dp.include_router(statistics.router)
    dp.include_router(user.router)

    # Init DB
    await db.init_db()

    # Seed initial admins from .env
    if ADMIN_IDS_RAW:
        for tid_str in ADMIN_IDS_RAW.split(","):
            tid_str = tid_str.strip()
            if tid_str.isdigit():
                await db.add_admin(int(tid_str), "", 0)
                logger.info(f"Admin seeded: {tid_str}")

    os.makedirs("files", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    os.makedirs("backups", exist_ok=True)

    logger.info("Bot starting...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
