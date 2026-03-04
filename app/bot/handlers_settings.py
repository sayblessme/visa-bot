from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import cities_kb, filters_kb, main_menu_kb
from app.bot.states import CredentialsFlow, SettingsFlow
from app.db import crud
from app.db.session import async_session_factory
from app.utils.i18n import normalize_city, country_display, city_display
from app.utils.crypto import encrypt_data
from app.config import settings

router = Router(name="settings")


# ── Country selection ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("country:"))
async def on_country_selected(callback: CallbackQuery) -> None:
    country = callback.data.split(":", 1)[1]
    async with async_session_factory() as session:
        await crud.upsert_preferences(session, callback.from_user.id, country=country)
        await session.commit()

    await callback.message.edit_text(f"Страна: {country_display(country)}")
    await callback.message.answer("Выберите город:", reply_markup=cities_kb(country))
    await callback.answer()


# ── City selection (inline buttons) ───────────────────────────────────

@router.callback_query(F.data.startswith("city:"))
async def on_city_selected(callback: CallbackQuery, state: FSMContext) -> None:
    city = callback.data.split(":", 1)[1]
    if city == "manual":
        await state.set_state(SettingsFlow.choosing_city)
        await callback.message.answer("Введите город (на русском или английском):")
        await callback.answer()
        return

    async with async_session_factory() as session:
        await crud.upsert_preferences(session, callback.from_user.id, city=city)
        await session.commit()

    await callback.message.edit_text(f"Город: {city_display(city)}")
    await callback.answer()


# ── Filter callbacks ───────────────────────────────────────────────────

@router.callback_query(F.data == "filter:city")
async def filter_city(callback: CallbackQuery, state: FSMContext) -> None:
    # Try to show city buttons based on selected country
    async with async_session_factory() as session:
        pref = await crud.get_preferences(session, callback.from_user.id)

    if pref and pref.country:
        await callback.message.answer(
            "Выберите город:", reply_markup=cities_kb(pref.country)
        )
    else:
        await state.set_state(SettingsFlow.choosing_city)
        await callback.message.answer("Введите город (на русском или английском):")
    await callback.answer()


@router.message(SettingsFlow.choosing_city)
async def set_city(message: Message, state: FSMContext) -> None:
    city_en = normalize_city(message.text.strip())
    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, city=city_en)
        await session.commit()
    await state.clear()
    await message.answer(f"Город: {city_display(city_en)}", reply_markup=main_menu_kb())


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
        "Введите дни недели через запятую:\nпн, вт, ср, чт, пт, сб, вс\n(или: mon, tue, wed, thu, fri, sat, sun)"
    )
    await callback.answer()


@router.message(SettingsFlow.choosing_weekdays)
async def set_weekdays(message: Message, state: FSMContext) -> None:
    ru_to_en = {"пн": "mon", "вт": "tue", "ср": "wed", "чт": "thu", "пт": "fri", "сб": "sat", "вс": "sun"}
    valid = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

    days = [d.strip().lower() for d in message.text.split(",")]
    # Convert Russian day names
    days = [ru_to_en.get(d, d) for d in days]
    filtered = [d for d in days if d in valid]

    if not filtered:
        await message.answer("Не распознано ни одного дня. Пример: пн, ср, пт")
        return

    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, weekdays=",".join(filtered))
        await session.commit()
    await state.clear()
    en_to_ru = {v: k for k, v in ru_to_en.items()}
    display = ", ".join(en_to_ru.get(d, d) for d in filtered)
    await message.answer(f"Дни недели: {display}", reply_markup=main_menu_kb())


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


# ── Provider credentials ──────────────────────────────────────────────

@router.message(F.text == "Учётные данные")
async def credentials_menu(message: Message) -> None:
    async with async_session_factory() as session:
        pref = await crud.get_preferences(session, message.from_user.id)

    email = pref.provider_email if pref else None
    has_pass = bool(pref and pref.provider_password_encrypted)

    text = (
        "Учётные данные визового центра\n"
        "(VFS Global / TLScontact / BLS Spain)\n\n"
        f"Email: {email or '— не задан'}\n"
        f"Пароль: {'установлен' if has_pass else '— не задан'}\n\n"
        "Введите /set_email чтобы задать email\n"
        "Введите /set_password чтобы задать пароль\n\n"
        "Данные шифруются и хранятся безопасно."
    )
    await message.answer(text, reply_markup=main_menu_kb())


@router.message(F.text == "/set_email")
async def cmd_set_email(message: Message, state: FSMContext) -> None:
    await state.set_state(CredentialsFlow.entering_email)
    await message.answer("Введите email от аккаунта визового центра:")


@router.message(CredentialsFlow.entering_email)
async def set_email(message: Message, state: FSMContext) -> None:
    email = message.text.strip()
    async with async_session_factory() as session:
        await crud.upsert_preferences(session, message.from_user.id, provider_email=email)
        await session.commit()
    await state.clear()
    # Delete the message with email for security
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(f"Email сохранён: {email}", reply_markup=main_menu_kb())


@router.message(F.text == "/set_password")
async def cmd_set_password(message: Message, state: FSMContext) -> None:
    await state.set_state(CredentialsFlow.entering_password)
    await message.answer(
        "Введите пароль от аккаунта визового центра.\n"
        "Сообщение будет удалено после сохранения."
    )


@router.message(CredentialsFlow.entering_password)
async def set_password(message: Message, state: FSMContext) -> None:
    password = message.text.strip()

    # Encrypt password
    key = settings.sessions_encryption_key
    if not key:
        await message.answer("Ошибка: ключ шифрования не настроен на сервере.")
        await state.clear()
        return

    encrypted = encrypt_data(password, key)

    async with async_session_factory() as session:
        await crud.upsert_preferences(
            session, message.from_user.id, provider_password_encrypted=encrypted
        )
        await session.commit()

    await state.clear()
    # Delete the message with password
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer("Пароль сохранён и зашифрован.", reply_markup=main_menu_kb())
