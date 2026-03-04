import datetime

import pytest
from sqlalchemy import select

from app.db.models import User, UserPreference
from app.db import crud


@pytest.mark.asyncio
async def test_get_or_create_user(async_session):
    """Create a new user and retrieve existing one."""
    user = await crud.get_or_create_user(async_session, tg_id=123456, username="testuser")
    assert user.id == 123456
    assert user.username == "testuser"

    # Second call returns the same user
    same = await crud.get_or_create_user(async_session, tg_id=123456, username="testuser")
    assert same.id == user.id


@pytest.mark.asyncio
async def test_upsert_preferences(async_session):
    """Create and update user preferences."""
    await crud.get_or_create_user(async_session, tg_id=100)

    # Create
    pref = await crud.upsert_preferences(
        async_session, user_id=100, country="Germany", city="Berlin"
    )
    assert pref.country == "Germany"
    assert pref.city == "Berlin"
    assert pref.applicants_count == 1

    # Update
    pref2 = await crud.upsert_preferences(
        async_session, user_id=100, city="Munich", applicants_count=3
    )
    assert pref2.country == "Germany"  # unchanged
    assert pref2.city == "Munich"  # updated
    assert pref2.applicants_count == 3


@pytest.mark.asyncio
async def test_get_preferences_none(async_session):
    """Returns None when no preferences exist."""
    await crud.get_or_create_user(async_session, tg_id=200)
    pref = await crud.get_preferences(async_session, 200)
    assert pref is None


@pytest.mark.asyncio
async def test_watch_crud(async_session):
    """Create watch, toggle enabled, check active watches."""
    await crud.get_or_create_user(async_session, tg_id=300)

    watch = await crud.get_or_create_watch(async_session, 300, "mock")
    assert watch.enabled is False

    watch.enabled = True
    await async_session.flush()

    active = await crud.get_active_watches(async_session)
    assert len(active) == 1
    assert active[0].user_id == 300
