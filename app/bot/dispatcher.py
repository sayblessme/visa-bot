from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers_start import router as start_router
from app.bot.handlers_menu import router as menu_router
from app.bot.handlers_settings import router as settings_router
from app.bot.handlers_monitoring import router as monitoring_router
from app.bot.handlers_booking import router as booking_router
from app.bot.handlers_vfs_token import router as vfs_token_router


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_routers(
        start_router,
        menu_router,
        settings_router,
        monitoring_router,
        booking_router,
        vfs_token_router,
    )
    return dp


def create_bot(token: str) -> Bot:
    return Bot(token=token)
