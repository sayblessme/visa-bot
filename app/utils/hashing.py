import hashlib

from app.providers.schemas import Slot


def slot_hash(slot: Slot) -> str:
    """Deterministic hash for slot deduplication."""
    raw = f"{slot.provider}:{slot.country}:{slot.center}:{slot.datetime_utc.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
