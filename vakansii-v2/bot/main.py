import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from bot.config import TELEGRAM_BOT_TOKEN
from bot.handlers.user_commands import router as user_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Точка входа Telegram-бота с graceful shutdown."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

    bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(user_router)

    def shutdown():
        logger.info("Получен сигнал завершения, останавливаем бота...")
        asyncio.create_task(dp.stop_polling())
        asyncio.create_task(bot.session.close())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
