"""
Test monitoring logic: slot detection -> dedup -> slot_seen creation.
"""

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.db import crud
from app.db.models import SlotSeen
from app.providers.schemas import Slot, MonitorCriteria
from app.utils.hashing import slot_hash


@pytest.mark.asyncio
async def test_slot_seen_created_on_new_slot(async_session):
    """When a new slot is found, a SlotSeen record is created."""
    await crud.get_or_create_user(async_session, tg_id=400)

    slot = Slot(
        provider="mock",
        country="Germany",
        center="Berlin VFS",
        datetime_utc=datetime.datetime(2026, 5, 10, 14, 0, tzinfo=datetime.UTC),
    )
    h = slot_hash(slot)

    # No existing record
    existing = await crud.find_recent_slot(async_session, 400, h, 30)
    assert existing is None

    # Create
    record = await crud.create_slot_seen(
        async_session,
        user_id=400,
        provider_name="mock",
        slot_hash=h,
        slot_datetime=slot.datetime_utc,
        center=slot.center,
        country=slot.country,
    )
    assert record.slot_hash == h
    assert record.user_id == 400
    assert record.country == "Germany"


@pytest.mark.asyncio
async def test_slot_dedup_skips_recent(async_session):
    """Recently notified slot is skipped by dedup check."""
    await crud.get_or_create_user(async_session, tg_id=500)

    slot = Slot(
        provider="mock",
        country="France",
        center="Paris TLS",
        datetime_utc=datetime.datetime(2026, 6, 1, 9, 0, tzinfo=datetime.UTC),
    )
    h = slot_hash(slot)

    # Create slot seen with recent notification
    await crud.create_slot_seen(
        async_session,
        user_id=500,
        provider_name="mock",
        slot_hash=h,
        slot_datetime=slot.datetime_utc,
        center=slot.center,
        country=slot.country,
    )
    await async_session.flush()

    # Dedup check should find it
    existing = await crud.find_recent_slot(async_session, 500, h, 30)
    assert existing is not None
    assert existing.slot_hash == h


@pytest.mark.asyncio
async def test_mock_provider_fetch():
    """MockProvider generates slots and respects criteria."""
    from app.providers.mock import MockProvider

    provider = MockProvider()
    criteria = MonitorCriteria(country="Italy", center="Rome VFS")

    # Run multiple times to get at least one result (30% chance each)
    all_slots = []
    for _ in range(20):
        slots = await provider.fetch_availability(criteria)
        all_slots.extend(slots)
        if slots:
            break

    # At least verify the provider returns valid Slot objects
    if all_slots:
        s = all_slots[0]
        assert s.provider == "mock"
        assert s.country == "Italy"
        assert isinstance(s.datetime_utc, datetime.datetime)
