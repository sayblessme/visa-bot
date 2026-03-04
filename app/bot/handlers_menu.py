from aiogram import F, Router
from aiogram.types import Message

from app.bot.keyboards import countries_kb, filters_kb

router = Router(name="menu")


@router.message(F.text == "Выбрать страну")
async def choose_country(message: Message) -> None:
    await message.answer("Выберите страну:", reply_markup=countries_kb())


@router.message(F.text == "Фильтры")
async def show_filters(message: Message) -> None:
    await message.answer(
        "Настройте фильтры мониторинга:",
        reply_markup=filters_kb(),
    )
