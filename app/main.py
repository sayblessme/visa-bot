import asyncio

import structlog

from app.config import settings
from app.logging import setup_logging
from app.bot.dispatcher import create_bot, create_dispatcher

log = structlog.get_logger()


async def main() -> None:
    setup_logging(settings.log_level)
    log.info("Starting visa-bot", log_level=settings.log_level)

    bot = create_bot(settings.bot_token)
    dp = create_dispatcher()

    # Set bot commands
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="continue", description="Продолжить бронирование"),
    ])

    log.info("Bot polling started")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
