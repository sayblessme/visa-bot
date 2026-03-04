import datetime

from app.providers.schemas import Slot
from app.utils.hashing import slot_hash


def test_slot_hash_deterministic():
    """Same slot data produces the same hash."""
    slot = Slot(
        provider="mock",
        country="Germany",
        center="Berlin VFS",
        datetime_utc=datetime.datetime(2026, 4, 15, 10, 30, tzinfo=datetime.UTC),
    )
    h1 = slot_hash(slot)
    h2 = slot_hash(slot)
    assert h1 == h2
    assert len(h1) == 16


def test_slot_hash_different_for_different_slots():
    """Different slots produce different hashes."""
    slot1 = Slot(
        provider="mock",
        country="Germany",
        center="Berlin VFS",
        datetime_utc=datetime.datetime(2026, 4, 15, 10, 30, tzinfo=datetime.UTC),
    )
    slot2 = Slot(
        provider="mock",
        country="Germany",
        center="Berlin VFS",
        datetime_utc=datetime.datetime(2026, 4, 16, 10, 30, tzinfo=datetime.UTC),
    )
    assert slot_hash(slot1) != slot_hash(slot2)


def test_slot_hash_dedup_same_data():
    """Slots with identical provider/country/center/datetime get same hash."""
    base = dict(
        provider="mock",
        country="France",
        center="Paris TLS",
        datetime_utc=datetime.datetime(2026, 5, 1, 9, 0, tzinfo=datetime.UTC),
    )
    # visa_type and url differ, but hash should be the same (dedup by core fields)
    slot_a = Slot(**base, visa_type="Schengen C", url="https://a.com")
    slot_b = Slot(**base, visa_type="National D", url="https://b.com")
    assert slot_hash(slot_a) == slot_hash(slot_b)
