from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards import main_menu_kb
from app.db import crud
from app.db.session import async_session_factory

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with async_session_factory() as session:
        await crud.get_or_create_user(
            session,
            tg_id=message.from_user.id,
            username=message.from_user.username,
        )
        await session.commit()

    await message.answer(
        "Привет! Я бот для мониторинга визовых слотов.\n\n"
        "Выберите действие в меню ниже:",
        reply_markup=main_menu_kb(),
    )
