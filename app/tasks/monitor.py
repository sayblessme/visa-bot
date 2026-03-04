"""
Monitoring tasks: dispatch checks for active watches and run individual checks.
"""

import asyncio
import datetime
import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.session import sync_session_factory
from app.db import crud
from app.db.models import Watch, UserPreference
from app.providers.registry import get_provider
from app.providers.schemas import MonitorCriteria
from app.tasks.celery_app import celery_app
from app.utils.crypto import decrypt_data
from app.utils.hashing import slot_hash

log = structlog.get_logger()

# Service account credentials per provider (from .env)
_SERVICE_ACCOUNTS: dict[str, tuple[str, str]] = {}


def _get_service_account(provider_name: str) -> tuple[str, str]:
    """Return (email, password) from .env for the given provider, or ('', '')."""
    if not _SERVICE_ACCOUNTS:
        _SERVICE_ACCOUNTS["vfs_global"] = (settings.vfs_email, settings.vfs_password)
        _SERVICE_ACCOUNTS["tlscontact"] = (settings.tls_email, settings.tls_password)
        _SERVICE_ACCOUNTS["bls_spain"] = (settings.bls_email, settings.bls_password)
    return _SERVICE_ACCOUNTS.get(provider_name, ("", ""))


@celery_app.task(name="app.tasks.monitor.dispatch_monitors")
def dispatch_monitors() -> int:
    """Called by Beat: find all active watches and enqueue individual check tasks."""
    with sync_session_factory() as session:
        watches = crud.get_active_watches_sync(session)
        count = 0
        for watch in watches:
            check_single_watch.delay(watch.id, watch.user_id, watch.provider_name)
            count += 1
    log.info("dispatch_monitors", dispatched=count)
    return count


@celery_app.task(
    name="app.tasks.monitor.check_single_watch",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def check_single_watch(self, watch_id: int, user_id: int, provider_name: str) -> dict:
    """Run a single monitoring check for a watch."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _async_check(self, watch_id, user_id, provider_name)
        )
    finally:
        loop.close()


async def _async_check(task, watch_id: int, user_id: int, provider_name: str) -> dict:
    provider = get_provider(provider_name)
    result = {"watch_id": watch_id, "user_id": user_id, "new_slots": 0, "errors": 0}

    # Create a fresh engine per task to avoid asyncpg pool conflicts in Celery forks
    engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Build criteria from user preferences (with credential fallback)
        pref = await crud.get_preferences(session, user_id)
        criteria = _build_criteria(pref, provider_name)

        try:
            slots = await provider.fetch_availability(criteria)
        except Exception as exc:
            log.error("monitor.fetch_error", watch_id=watch_id, error=str(exc))
            result["errors"] = 1
            return result
        finally:
            await provider.close()

        # Update last_check_at
        await crud.update_watch_last_check(session, watch_id)

        # Process each slot
        new_slots = []
        for slot in slots:
            h = slot_hash(slot)

            # Dedup: skip if already notified recently
            existing = await crud.find_recent_slot(
                session, user_id, h, settings.slot_dedup_minutes
            )
            if existing is not None:
                continue

            # Record slot
            await crud.create_slot_seen(
                session,
                user_id=user_id,
                provider_name=provider_name,
                slot_hash=h,
                slot_datetime=slot.datetime_utc,
                center=slot.center,
                country=slot.country,
            )
            new_slots.append(slot)

        await session.commit()

        # Send notifications and possibly trigger booking
        if new_slots:
            watch = await crud.get_watch(session, user_id)
            for slot in new_slots:
                _send_notification.delay(
                    user_id,
                    slot.display,
                    slot_hash(slot),
                    provider_name,
                    watch.auto_book if watch else False,
                    json.dumps({
                        "provider": slot.provider,
                        "country": slot.country,
                        "center": slot.center,
                        "datetime_utc": slot.datetime_utc.isoformat(),
                        "visa_type": slot.visa_type,
                        "url": slot.url,
                    }),
                )

        result["new_slots"] = len(new_slots)

    await engine.dispose()
    return result


@celery_app.task(name="app.tasks.monitor.send_notification")
def _send_notification(
    user_id: int,
    slot_display: str,
    s_hash: str,
    provider_name: str,
    auto_book: bool,
    slot_json: str,
) -> None:
    """Send Telegram notification about a found slot. Optionally trigger booking."""
    import httpx
    from app.config import settings as cfg

    text = f"Найден слот!\n\n{slot_display}"
    if auto_book:
        text += "\n\nАвтозапись включена — запускаю бронирование..."

    # Send via Telegram Bot API directly (from Celery worker context)
    url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
    try:
        with httpx.Client(timeout=10) as client:
            client.post(url, json={"chat_id": user_id, "text": text})
    except Exception as exc:
        log.error("send_notification.failed", user_id=user_id, error=str(exc))

    # Trigger auto-booking if enabled
    if auto_book:
        from app.tasks.book import start_booking
        start_booking.delay(user_id, s_hash, provider_name, slot_json)


def _build_criteria(pref: UserPreference | None, provider_name: str = "") -> MonitorCriteria:
    if pref is None:
        return MonitorCriteria()

    weekdays = pref.weekdays.split(",") if pref.weekdays else None

    # Resolve credentials: user's own → service account fallback
    email = pref.provider_email or ""
    password = ""
    if pref.provider_password_encrypted and settings.sessions_encryption_key:
        try:
            password = decrypt_data(pref.provider_password_encrypted, settings.sessions_encryption_key)
        except Exception:
            password = ""

    # Fallback to service account if user has no credentials
    if not email or not password:
        svc_email, svc_password = _get_service_account(provider_name)
        if svc_email and svc_password:
            email = svc_email
            password = svc_password
            log.info("monitor.using_service_account", provider=provider_name)

    return MonitorCriteria(
        country=pref.country,
        city=pref.city,
        center=pref.center,
        visa_type=pref.visa_type,
        date_from=pref.date_from,
        date_to=pref.date_to,
        weekdays=weekdays,
        time_from=pref.time_from,
        time_to=pref.time_to,
        applicants_count=pref.applicants_count,
        email=email or None,
        password=password or None,
    )
