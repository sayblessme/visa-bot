"""
Handler for /vfs_token — manual VFS token input.

When auto-refresh fails (CAPTCHA, Cloudflare), the user can paste
authorize and clientsource tokens from their browser DevTools.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards import main_menu_kb
from app.bot.states import VfsTokenFlow
from app.config import settings
from app.tasks.vfs_token_refresh import save_vfs_tokens

router = Router(name="vfs_token")


@router.message(Command("vfs_token"))
async def cmd_vfs_token(message: Message, state: FSMContext) -> None:
    await state.set_state(VfsTokenFlow.entering_authorize)
    await message.answer(
        "Введите токен VFS (заголовок `authorize` из DevTools).\n\n"
        "Как найти:\n"
        "1. Откройте visa.vfsglobal.com → залогиньтесь\n"
        "2. F12 → Network → найдите запрос к lift-api.vfsglobal.com\n"
        "3. Скопируйте значение заголовка `authorize`\n\n"
        "Он начинается с EAAAA..."
    )


@router.message(VfsTokenFlow.entering_authorize)
async def set_authorize(message: Message, state: FSMContext) -> None:
    authorize = message.text.strip()
    if len(authorize) < 20:
        await message.answer("Токен слишком короткий. Попробуйте ещё раз.")
        return

    await state.update_data(authorize=authorize)
    await state.set_state(VfsTokenFlow.entering_clientsource)

    # Delete the message with token for security
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        "Токен authorize сохранён.\n\n"
        "Теперь введите значение заголовка `clientsource` из того же запроса:"
    )


@router.message(VfsTokenFlow.entering_clientsource)
async def set_clientsource(message: Message, state: FSMContext) -> None:
    clientsource = message.text.strip()
    if len(clientsource) < 10:
        await message.answer("Значение слишком короткое. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    authorize = data.get("authorize", "")

    route = settings.vfs_route or "kaz/ru/aut"

    save_vfs_tokens(
        authorize=authorize,
        clientsource=clientsource,
        route=route,
    )

    await state.clear()

    # Delete the message with token for security
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        "Токены VFS сохранены в Redis (TTL 30 мин).\n"
        "Мониторинг будет использовать эти токены для API-запросов.\n\n"
        "Бот попытается обновить их автоматически при следующем цикле.",
        reply_markup=main_menu_kb(),
    )
