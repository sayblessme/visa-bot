from aiogram import F, Router
from aiogram.types import Message

from app.bot.keyboards import main_menu_kb
from app.db import crud
from app.db.session import async_session_factory

router = Router(name="monitoring")


@router.message(F.text == "Включить мониторинг")
async def enable_monitoring(message: Message) -> None:
    async with async_session_factory() as session:
        watch = await crud.get_or_create_watch(session, message.from_user.id)
        watch.enabled = True
        await session.commit()

    await message.answer(
        "Мониторинг включен. Я буду проверять слоты и уведомлять вас.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "Выключить мониторинг")
async def disable_monitoring(message: Message) -> None:
    async with async_session_factory() as session:
        watch = await crud.get_or_create_watch(session, message.from_user.id)
        watch.enabled = False
        await session.commit()

    await message.answer(
        "Мониторинг выключен.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "Автозапись: Вкл")
async def enable_autobook(message: Message) -> None:
    async with async_session_factory() as session:
        watch = await crud.get_or_create_watch(session, message.from_user.id)
        watch.auto_book = True
        await session.commit()

    await message.answer(
        "Автозапись включена. При нахождении слота я автоматически попытаюсь забронировать.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "Автозапись: Выкл")
async def disable_autobook(message: Message) -> None:
    async with async_session_factory() as session:
        watch = await crud.get_or_create_watch(session, message.from_user.id)
        watch.auto_book = False
        await session.commit()

    await message.answer(
        "Автозапись выключена.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "Статус")
async def show_status(message: Message) -> None:
    async with async_session_factory() as session:
        pref = await crud.get_preferences(session, message.from_user.id)
        watch = await crud.get_watch(session, message.from_user.id)

    lines = ["Текущий статус:\n"]

    if pref:
        lines.append(f"Страна: {pref.country or '—'}")
        lines.append(f"Город: {pref.city or '—'}")
        lines.append(f"Центр: {pref.center or '—'}")
        lines.append(f"Тип визы: {pref.visa_type or '—'}")
        if pref.date_from:
            lines.append(f"Дата от: {pref.date_from.strftime('%d.%m.%Y')}")
        if pref.date_to:
            lines.append(f"Дата до: {pref.date_to.strftime('%d.%m.%Y')}")
        if pref.weekdays:
            lines.append(f"Дни: {pref.weekdays}")
        lines.append(f"Заявителей: {pref.applicants_count}")
    else:
        lines.append("Настройки не заданы.")

    lines.append("")

    if watch:
        lines.append(f"Мониторинг: {'включен' if watch.enabled else 'выключен'}")
        lines.append(f"Автозапись: {'да' if watch.auto_book else 'нет'}")
        lines.append(f"Провайдер: {watch.provider_name}")
        if watch.last_check_at:
            lines.append(f"Последняя проверка: {watch.last_check_at.strftime('%d.%m.%Y %H:%M UTC')}")
    else:
        lines.append("Мониторинг не настроен.")

    await message.answer("\n".join(lines), reply_markup=main_menu_kb())
