import datetime
import random

from app.providers.base import BaseProvider
from app.providers.schemas import BookingResult, BookingStatus, MonitorCriteria, Slot


class MockProvider(BaseProvider):
    """Mock provider that generates random slots for end-to-end testing."""

    name: str = "mock"

    def __init__(self) -> None:
        self._call_count = 0

    async def fetch_availability(self, criteria: MonitorCriteria) -> list[Slot]:
        self._call_count += 1

        # Generate slots on ~30% of checks to simulate real behavior
        if random.random() > 0.3:
            return []

        country = criteria.country or "Germany"
        center = criteria.center or "Berlin VFS"
        now = datetime.datetime.now(datetime.UTC)

        num_slots = random.randint(1, 3)
        slots: list[Slot] = []
        for i in range(num_slots):
            slot_dt = now + datetime.timedelta(
                days=random.randint(3, 30),
                hours=random.randint(8, 16),
                minutes=random.choice([0, 15, 30, 45]),
            )

            # Apply date filters if provided
            if criteria.date_from and slot_dt.date() < criteria.date_from:
                continue
            if criteria.date_to and slot_dt.date() > criteria.date_to:
                continue

            slots.append(
                Slot(
                    provider=self.name,
                    country=country,
                    center=center,
                    datetime_utc=slot_dt,
                    visa_type=criteria.visa_type or "Schengen C",
                    url="https://example.com/mock-booking",
                )
            )

        return slots

    async def book(self, slot: Slot, user_profile: dict) -> BookingResult:
        # Simulate: 50% instant success, 30% need user action (captcha), 20% fail
        roll = random.random()
        if roll < 0.5:
            return BookingResult(
                status=BookingStatus.SUCCESS,
                message="Mock booking confirmed!",
                details={
                    "confirmation_code": f"MOCK-{random.randint(10000, 99999)}",
                    "slot": slot.display,
                },
            )
        elif roll < 0.8:
            return BookingResult(
                status=BookingStatus.NEED_USER_ACTION,
                message="Please solve the captcha and click 'Continue'.",
                details={"action_type": "captcha", "captcha_url": "https://example.com/captcha"},
            )
        else:
            return BookingResult(
                status=BookingStatus.FAILED,
                message="Slot was already taken by another applicant.",
                details={"reason": "slot_taken"},
            )
