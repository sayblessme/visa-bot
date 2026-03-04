from aiogram import F, Router
from aiogram.types import Message

from app.bot.keyboards import main_menu_kb
from app.db import crud
from app.db.session import async_session_factory
from app.utils.i18n import country_display, city_display

router = Router(name="monitoring")

PROVIDER_LABELS = {
    "mock": "Mock (тест)",
    "vfs_global": "VFS Global",
    "tlscontact": "TLScontact",
    "bls_spain": "BLS Spain",
}


@router.message(F.text == "Включить мониторинг")
async def enable_monitoring(message: Message) -> None:
    async with async_session_factory() as session:
        pref = await crud.get_preferences(session, message.from_user.id)
        watch = await crud.get_or_create_watch(session, message.from_user.id)

        if not pref or not pref.country:
            await message.answer(
                "Сначала выберите страну и провайдера!", reply_markup=main_menu_kb()
            )
            return

        watch.enabled = True
        await session.commit()
        provider = PROVIDER_LABELS.get(watch.provider_name, watch.provider_name)

    await message.answer(
        f"Мониторинг включен ({provider}).\n"
        "Проверяю слоты каждые 1-3 минуты. Уведомлю о появлении.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "Выключить мониторинг")
async def disable_monitoring(message: Message) -> None:
    async with async_session_factory() as session:
        watch = await crud.get_or_create_watch(session, message.from_user.id)
        watch.enabled = False
        await session.commit()

    await message.answer("Мониторинг выключен.", reply_markup=main_menu_kb())


@router.message(F.text == "Автозапись: Вкл")
async def enable_autobook(message: Message) -> None:
    async with async_session_factory() as session:
        watch = await crud.get_or_create_watch(session, message.from_user.id)
        watch.auto_book = True
        await session.commit()

    await message.answer(
        "Автозапись включена.\nПри нахождении слота — автоматическая попытка бронирования.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "Автозапись: Выкл")
async def disable_autobook(message: Message) -> None:
    async with async_session_factory() as session:
        watch = await crud.get_or_create_watch(session, message.from_user.id)
        watch.auto_book = False
        await session.commit()

    await message.answer("Автозапись выключена.", reply_markup=main_menu_kb())


@router.message(F.text == "Статус")
async def show_status(message: Message) -> None:
    async with async_session_factory() as session:
        pref = await crud.get_preferences(session, message.from_user.id)
        watch = await crud.get_watch(session, message.from_user.id)

    lines = ["Текущий статус:\n"]

    if pref:
        lines.append(f"Страна: {country_display(pref.country) if pref.country else '—'}")
        lines.append(f"Город: {city_display(pref.city) if pref.city else '—'}")
        if pref.center:
            lines.append(f"Центр: {pref.center}")
        lines.append(f"Тип визы: {pref.visa_type or '—'}")
        if pref.date_from:
            lines.append(f"Дата от: {pref.date_from.strftime('%d.%m.%Y')}")
        if pref.date_to:
            lines.append(f"Дата до: {pref.date_to.strftime('%d.%m.%Y')}")
        if pref.weekdays:
            lines.append(f"Дни: {pref.weekdays}")
        lines.append(f"Заявителей: {pref.applicants_count}")
        lines.append(f"Email: {pref.provider_email or '— не задан'}")
        lines.append(f"Пароль: {'установлен' if pref.provider_password_encrypted else '— не задан'}")
    else:
        lines.append("Настройки не заданы.")

    lines.append("")

    if watch:
        provider = PROVIDER_LABELS.get(watch.provider_name, watch.provider_name)
        lines.append(f"Провайдер: {provider}")
        lines.append(f"Мониторинг: {'включен' if watch.enabled else 'выключен'}")
        lines.append(f"Автозапись: {'да' if watch.auto_book else 'нет'}")
        if watch.last_check_at:
            lines.append(f"Последняя проверка: {watch.last_check_at.strftime('%d.%m.%Y %H:%M UTC')}")
    else:
        lines.append("Мониторинг не настроен.")

    await message.answer("\n".join(lines), reply_markup=main_menu_kb())
