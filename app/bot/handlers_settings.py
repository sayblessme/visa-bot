from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import filters_kb, main_menu_kb
from app.bot.states import SettingsFlow
from app.db import crud
from app.db.session import async_session_factory

router = Router(name="settings")


# ── Country selection ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("country:"))
async def on_country_selected(callback: CallbackQuery) -> None:
    country = callback.data.split(":", 1)[1]
    async with async_session_factory() as session:
        await crud.upsert_preferences(session, callback.from_user.id, country=country)
        await session.commit()

    await callback.message.edit_text(f"Страна установлена: {country}")
    await callback.answer()


# ── Filter callbacks ───────────────────────────────────────────────────

@router.callback_query(F.data == "filter:city")
async def filter_city(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.choosing_city)
    await callback.message.answer("Введите город:")
    await callback.answer()


@router.message(SettingsFlow.choosing_city)
async def set_city(message: Message, state: FSMContext) -> None:
    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, city=message.text.strip())
        await session.commit()
    await state.clear()
    await message.answer(f"Город: {message.text.strip()}", reply_markup=main_menu_kb())


@router.callback_query(F.data == "filter:center")
async def filter_center(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.choosing_center)
    await callback.message.answer("Введите название визового центра:")
    await callback.answer()


@router.message(SettingsFlow.choosing_center)
async def set_center(message: Message, state: FSMContext) -> None:
    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, center=message.text.strip())
        await session.commit()
    await state.clear()
    await message.answer(f"Центр: {message.text.strip()}", reply_markup=main_menu_kb())


@router.callback_query(F.data == "filter:visa_type")
async def filter_visa_type(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.choosing_visa_type)
    await callback.message.answer("Введите тип визы (например: Schengen C, National D):")
    await callback.answer()


@router.message(SettingsFlow.choosing_visa_type)
async def set_visa_type(message: Message, state: FSMContext) -> None:
    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, visa_type=message.text.strip())
        await session.commit()
    await state.clear()
    await message.answer(f"Тип визы: {message.text.strip()}", reply_markup=main_menu_kb())


@router.callback_query(F.data == "filter:date_from")
async def filter_date_from(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.choosing_date_from)
    await callback.message.answer("Введите дату начала (ДД.ММ.ГГГГ):")
    await callback.answer()


@router.message(SettingsFlow.choosing_date_from)
async def set_date_from(message: Message, state: FSMContext) -> None:
    import datetime

    try:
        dt = datetime.datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат. Используйте ДД.ММ.ГГГГ")
        return

    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, date_from=dt)
        await session.commit()
    await state.clear()
    await message.answer(f"Дата от: {dt.strftime('%d.%m.%Y')}", reply_markup=main_menu_kb())


@router.callback_query(F.data == "filter:date_to")
async def filter_date_to(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.choosing_date_to)
    await callback.message.answer("Введите дату окончания (ДД.ММ.ГГГГ):")
    await callback.answer()


@router.message(SettingsFlow.choosing_date_to)
async def set_date_to(message: Message, state: FSMContext) -> None:
    import datetime

    try:
        dt = datetime.datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат. Используйте ДД.ММ.ГГГГ")
        return

    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, date_to=dt)
        await session.commit()
    await state.clear()
    await message.answer(f"Дата до: {dt.strftime('%d.%m.%Y')}", reply_markup=main_menu_kb())


@router.callback_query(F.data == "filter:weekdays")
async def filter_weekdays(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.choosing_weekdays)
    await callback.message.answer(
        "Введите дни недели через запятую (mon,tue,wed,thu,fri,sat,sun):"
    )
    await callback.answer()


@router.message(SettingsFlow.choosing_weekdays)
async def set_weekdays(message: Message, state: FSMContext) -> None:
    valid = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    days = [d.strip().lower() for d in message.text.split(",")]
    filtered = [d for d in days if d in valid]
    if not filtered:
        await message.answer("Не распознано ни одного дня. Используйте: mon,tue,wed,thu,fri,sat,sun")
        return

    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, weekdays=",".join(filtered))
        await session.commit()
    await state.clear()
    await message.answer(f"Дни недели: {', '.join(filtered)}", reply_markup=main_menu_kb())


@router.callback_query(F.data == "filter:applicants")
async def filter_applicants(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.choosing_applicants)
    await callback.message.answer("Введите количество заявителей:")
    await callback.answer()


@router.message(SettingsFlow.choosing_applicants)
async def set_applicants(message: Message, state: FSMContext) -> None:
    try:
        count = int(message.text.strip())
        if count < 1:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число больше 0")
        return

    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, applicants_count=count)
        await session.commit()
    await state.clear()
    await message.answer(f"Заявителей: {count}", reply_markup=main_menu_kb())


@router.callback_query(F.data == "filter:done")
async def filter_done(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Фильтры сохранены.")
    await callback.answer()
