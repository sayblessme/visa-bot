from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import main_menu_kb
from app.bot.states import BookingFlow
from app.db import crud
from app.db.session import async_session_factory
from app.tasks.book import resume_booking

router = Router(name="booking")


@router.message(F.text == "История попыток")
async def show_history(message: Message) -> None:
    async with async_session_factory() as session:
        attempts = await crud.get_booking_attempts(session, message.from_user.id)

    if not attempts:
        await message.answer("Нет попыток бронирования.", reply_markup=main_menu_kb())
        return

    lines = ["Последние попытки бронирования:\n"]
    for a in attempts:
        dt = a.created_at.strftime("%d.%m.%Y %H:%M") if a.created_at else "—"
        lines.append(f"#{a.id} | {a.provider_name} | {a.status} | {dt}")

    await message.answer("\n".join(lines), reply_markup=main_menu_kb())


@router.callback_query(F.data.startswith("booking_continue:"))
async def booking_continue(callback: CallbackQuery) -> None:
    attempt_id = int(callback.data.split(":")[1])
    resume_booking.delay(attempt_id, callback.from_user.id, "user_confirmed")
    await callback.message.edit_text(
        f"Продолжаю бронирование #{attempt_id}... Ожидайте результат."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("booking_code:"))
async def booking_code_request(callback: CallbackQuery, state: FSMContext) -> None:
    attempt_id = int(callback.data.split(":")[1])
    await state.set_state(BookingFlow.entering_code)
    await state.update_data(attempt_id=attempt_id)
    await callback.message.answer("Введите код:")
    await callback.answer()


@router.message(BookingFlow.entering_code)
async def booking_code_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    attempt_id = data.get("attempt_id")
    if attempt_id is None:
        await message.answer("Ошибка: попытка не найдена.", reply_markup=main_menu_kb())
        await state.clear()
        return

    resume_booking.delay(attempt_id, message.from_user.id, message.text.strip())
    await state.clear()
    await message.answer(
        f"Код отправлен. Продолжаю бронирование #{attempt_id}...",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "/continue")
async def cmd_continue(message: Message) -> None:
    """Fallback /continue command to resume the latest pending booking."""
    async with async_session_factory() as session:
        attempts = await crud.get_booking_attempts(session, message.from_user.id, limit=1)

    if not attempts:
        await message.answer("Нет активных бронирований.", reply_markup=main_menu_kb())
        return

    latest = attempts[0]
    if latest.status != "need_user_action":
        await message.answer(
            f"Последнее бронирование #{latest.id} в статусе '{latest.status}'.",
            reply_markup=main_menu_kb(),
        )
        return

    resume_booking.delay(latest.id, message.from_user.id, "user_confirmed")
    await message.answer(
        f"Продолжаю бронирование #{latest.id}...",
        reply_markup=main_menu_kb(),
    )
