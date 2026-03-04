from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import countries_kb, filters_kb, main_menu_kb, providers_kb
from app.db import crud
from app.db.session import async_session_factory

router = Router(name="menu")


@router.message(F.text == "Выбрать провайдера")
async def choose_provider(message: Message) -> None:
    await message.answer("Выберите визовый сервис:", reply_markup=providers_kb())


@router.callback_query(F.data.startswith("provider:"))
async def on_provider_selected(callback: CallbackQuery) -> None:
    provider_name = callback.data.split(":", 1)[1]
    labels = {"vfs_global": "VFS Global", "tlscontact": "TLScontact", "mock": "Mock (тест)"}
    async with async_session_factory() as session:
        watch = await crud.get_or_create_watch(session, callback.from_user.id, provider_name)
        watch.provider_name = provider_name
        await session.commit()

    await callback.message.edit_text(f"Провайдер: {labels.get(provider_name, provider_name)}")
    await callback.answer()


@router.message(F.text == "Выбрать страну")
async def choose_country(message: Message) -> None:
    await message.answer("Выберите страну:", reply_markup=countries_kb())


@router.message(F.text == "Фильтры")
async def show_filters(message: Message) -> None:
    await message.answer(
        "Настройте фильтры мониторинга:",
        reply_markup=filters_kb(),
    )
