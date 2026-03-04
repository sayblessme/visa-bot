"""
Booking tasks: attempt to book a slot, handle human-in-the-loop flow.
"""

import asyncio
import json
import datetime

import structlog

from app.config import settings
from app.db.session import async_session_factory
from app.db import crud
from app.providers.registry import get_provider
from app.providers.schemas import BookingStatus, Slot
from app.tasks.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="app.tasks.book.start_booking", bind=True, max_retries=2)
def start_booking(
    self, user_id: int, s_hash: str, provider_name: str, slot_json: str
) -> dict:
    """Start a booking attempt for a found slot."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _async_book(self, user_id, s_hash, provider_name, slot_json)
        )
    finally:
        loop.close()


async def _async_book(
    task, user_id: int, s_hash: str, provider_name: str, slot_json: str
) -> dict:
    slot_data = json.loads(slot_json)
    slot = Slot(
        provider=slot_data["provider"],
        country=slot_data["country"],
        center=slot_data["center"],
        datetime_utc=datetime.datetime.fromisoformat(slot_data["datetime_utc"]),
        visa_type=slot_data.get("visa_type", ""),
        url=slot_data.get("url", ""),
    )

    async with async_session_factory() as session:
        # Create booking attempt with transactional lock
        attempt = await crud.create_booking_attempt(
            session, user_id, provider_name, s_hash, status="started"
        )
        await session.commit()
        attempt_id = attempt.id

    # Run the actual booking
    provider = get_provider(provider_name)
    try:
        result = await provider.book(slot, {"user_id": user_id})
    except Exception as exc:
        log.error("booking.error", user_id=user_id, slot_hash=s_hash, error=str(exc))
        async with async_session_factory() as session:
            await crud.update_booking_status(
                session, attempt_id, "failed", json.dumps({"error": str(exc)})
            )
            await session.commit()
        return {"attempt_id": attempt_id, "status": "failed", "error": str(exc)}
    finally:
        await provider.close()

    # Update attempt based on result
    async with async_session_factory() as session:
        await crud.update_booking_status(
            session, attempt_id, result.status.value, json.dumps(result.details)
        )
        await session.commit()

    # Notify user about result
    _notify_booking_result(user_id, attempt_id, result.status.value, result.message)

    return {"attempt_id": attempt_id, "status": result.status.value}


def _notify_booking_result(
    user_id: int, attempt_id: int, status: str, message: str
) -> None:
    import httpx
    from app.config import settings as cfg

    status_emoji = {
        "success": "OK",
        "failed": "FAIL",
        "need_user_action": "ACTION REQUIRED",
    }

    text = f"[{status_emoji.get(status, status)}] Бронирование #{attempt_id}\n\n{message}"

    if status == "need_user_action":
        text += "\n\nНажмите /continue после выполнения действия."

    url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
    try:
        with httpx.Client(timeout=10) as client:
            client.post(url, json={"chat_id": user_id, "text": text})
    except Exception as exc:
        log.error("notify_booking.failed", user_id=user_id, error=str(exc))


@celery_app.task(name="app.tasks.book.resume_booking", bind=True)
def resume_booking(self, attempt_id: int, user_id: int, user_input: str = "") -> dict:
    """Resume a booking attempt after user action (captcha/code/confirmation)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _async_resume(attempt_id, user_id, user_input)
        )
    finally:
        loop.close()


async def _async_resume(attempt_id: int, user_id: int, user_input: str) -> dict:
    async with async_session_factory() as session:
        attempt = await crud.get_pending_booking(session, attempt_id)
        if attempt is None:
            return {"error": "Booking attempt not found"}

        if attempt.status != "need_user_action":
            return {"error": f"Attempt is in status '{attempt.status}', cannot resume"}

        # In a real provider, we would restore the browser session and continue.
        # For mock, we simulate success after user action.
        provider = get_provider(attempt.provider_name)
        try:
            # Mock: after user action, booking succeeds
            slot_data = json.loads(attempt.details_json) if attempt.details_json else {}
            await crud.update_booking_status(
                session,
                attempt_id,
                "success",
                json.dumps({**slot_data, "resumed": True, "user_input": user_input}),
            )
            await session.commit()
        finally:
            await provider.close()

    _notify_booking_result(user_id, attempt_id, "success", "Бронирование подтверждено после вашего действия!")
    return {"attempt_id": attempt_id, "status": "success"}
