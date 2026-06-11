import asyncio
import logging
import sys

# Pyrogram 2.x создаёт sync-обёртки при импорте и требует event loop (Python 3.10+).
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from bot.bot import create_bot, create_dispatcher
from bot.handlers import account, admin, broadcast, people, settings, start
from bot.middlewares.access import AccessMiddleware
from database.database import init_db
import config

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN не задан в .env")
        sys.exit(1)

    await init_db()

    bot = create_bot()
    dp = create_dispatcher()

    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(account.router)
    dp.include_router(settings.router)
    dp.include_router(broadcast.router)
    dp.include_router(people.router)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
