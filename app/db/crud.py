import datetime
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models import (
    BookingAttempt,
    SlotSeen,
    User,
    UserPreference,
    Watch,
)


# ── Users ──────────────────────────────────────────────────────────────

async def get_or_create_user(
    session: AsyncSession, tg_id: int, username: str | None = None
) -> User:
    result = await session.execute(select(User).where(User.id == tg_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(id=tg_id, username=username)
        session.add(user)
        await session.flush()
    return user


# ── Preferences ────────────────────────────────────────────────────────

async def get_preferences(session: AsyncSession, user_id: int) -> UserPreference | None:
    result = await session.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def upsert_preferences(
    session: AsyncSession, user_id: int, **kwargs
) -> UserPreference:
    pref = await get_preferences(session, user_id)
    if pref is None:
        pref = UserPreference(user_id=user_id, **kwargs)
        session.add(pref)
    else:
        for k, v in kwargs.items():
            setattr(pref, k, v)
    await session.flush()
    return pref


# ── Watches ────────────────────────────────────────────────────────────

async def get_watch(session: AsyncSession, user_id: int) -> Watch | None:
    result = await session.execute(
        select(Watch).where(Watch.user_id == user_id).order_by(Watch.id.desc())
    )
    return result.scalars().first()


async def get_or_create_watch(
    session: AsyncSession, user_id: int, provider_name: str = "mock"
) -> Watch:
    watch = await get_watch(session, user_id)
    if watch is None:
        watch = Watch(user_id=user_id, provider_name=provider_name)
        session.add(watch)
        await session.flush()
    return watch


async def get_active_watches(session: AsyncSession) -> Sequence[Watch]:
    result = await session.execute(select(Watch).where(Watch.enabled.is_(True)))
    return result.scalars().all()


def get_active_watches_sync(session: Session) -> Sequence[Watch]:
    result = session.execute(select(Watch).where(Watch.enabled.is_(True)))
    return result.scalars().all()


async def update_watch_last_check(session: AsyncSession, watch_id: int) -> None:
    await session.execute(
        update(Watch)
        .where(Watch.id == watch_id)
        .values(last_check_at=datetime.datetime.now(datetime.UTC))
    )
    await session.flush()


# ── Slots seen ─────────────────────────────────────────────────────────

async def find_recent_slot(
    session: AsyncSession, user_id: int, slot_hash: str, dedup_minutes: int = 30
) -> SlotSeen | None:
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=dedup_minutes)
    result = await session.execute(
        select(SlotSeen).where(
            SlotSeen.user_id == user_id,
            SlotSeen.slot_hash == slot_hash,
            SlotSeen.last_notified_at > cutoff,
        )
    )
    return result.scalar_one_or_none()


async def create_slot_seen(
    session: AsyncSession,
    user_id: int,
    provider_name: str,
    slot_hash: str,
    slot_datetime: datetime.datetime,
    center: str | None = None,
    country: str | None = None,
) -> SlotSeen:
    now = datetime.datetime.now(datetime.UTC)
    slot = SlotSeen(
        user_id=user_id,
        provider_name=provider_name,
        slot_hash=slot_hash,
        slot_datetime=slot_datetime,
        center=center,
        country=country,
        first_seen_at=now,
        last_notified_at=now,
    )
    session.add(slot)
    await session.flush()
    return slot


# ── Booking attempts ──────────────────────────────────────────────────

async def create_booking_attempt(
    session: AsyncSession,
    user_id: int,
    provider_name: str,
    slot_hash: str,
    status: str = "started",
) -> BookingAttempt:
    attempt = BookingAttempt(
        user_id=user_id,
        provider_name=provider_name,
        slot_hash=slot_hash,
        status=status,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def update_booking_status(
    session: AsyncSession, attempt_id: int, status: str, details: str | None = None
) -> None:
    await session.execute(
        update(BookingAttempt)
        .where(BookingAttempt.id == attempt_id)
        .values(status=status, details_json=details)
    )
    await session.flush()


async def get_booking_attempts(
    session: AsyncSession, user_id: int, limit: int = 10
) -> Sequence[BookingAttempt]:
    result = await session.execute(
        select(BookingAttempt)
        .where(BookingAttempt.user_id == user_id)
        .order_by(BookingAttempt.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_pending_booking(
    session: AsyncSession, attempt_id: int
) -> BookingAttempt | None:
    result = await session.execute(
        select(BookingAttempt).where(BookingAttempt.id == attempt_id)
    )
    return result.scalar_one_or_none()
