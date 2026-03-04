import abc

from app.providers.schemas import BookingResult, MonitorCriteria, Slot


class BaseProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def fetch_availability(self, criteria: MonitorCriteria) -> list[Slot]:
        """Return list of available slots matching the criteria."""
        ...

    @abc.abstractmethod
    async def book(self, slot: Slot, user_profile: dict) -> BookingResult:
        """Attempt to book a slot. Returns BookingResult with status."""
        ...

    async def close(self) -> None:
        """Cleanup resources (browser contexts, etc.)."""
        pass
