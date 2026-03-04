import datetime
from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Slot:
    provider: str
    country: str
    center: str
    datetime_utc: datetime.datetime
    visa_type: str = ""
    url: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def display(self) -> str:
        dt = self.datetime_utc.strftime("%d.%m.%Y %H:%M")
        parts = [
            f"Провайдер: {self.provider}",
            f"Страна: {self.country}",
            f"Центр: {self.center}",
            f"Дата/время: {dt}",
        ]
        if self.visa_type:
            parts.append(f"Тип визы: {self.visa_type}")
        if self.url:
            parts.append(f"Ссылка: {self.url}")
        return "\n".join(parts)


class BookingStatus(str, Enum):
    STARTED = "started"
    NEED_USER_ACTION = "need_user_action"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class BookingResult:
    status: BookingStatus
    message: str = ""
    attempt_id: int | None = None
    details: dict = field(default_factory=dict)


@dataclass
class MonitorCriteria:
    country: str | None = None
    city: str | None = None
    center: str | None = None
    visa_type: str | None = None
    date_from: datetime.date | None = None
    date_to: datetime.date | None = None
    weekdays: list[str] | None = None
    time_from: datetime.time | None = None
    time_to: datetime.time | None = None
    applicants_count: int = 1
