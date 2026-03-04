import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    preferences: Mapped["UserPreference | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    watches: Mapped[list["Watch"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    center: Mapped[str | None] = mapped_column(String(256), nullable=True)
    visa_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date_from: Mapped[datetime.date | None] = mapped_column(nullable=True)
    date_to: Mapped[datetime.date | None] = mapped_column(nullable=True)
    weekdays: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # comma-separated: "mon,tue,wed"
    time_from: Mapped[datetime.time | None] = mapped_column(nullable=True)
    time_to: Mapped[datetime.time | None] = mapped_column(nullable=True)
    applicants_count: Mapped[int] = mapped_column(Integer, default=1)
    provider_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider_password_encrypted: Mapped[bytes | None] = mapped_column(nullable=True)

    user: Mapped["User"] = relationship(back_populates="preferences")


class Watch(Base):
    __tablename__ = "watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    provider_name: Mapped[str] = mapped_column(String(128), default="mock")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_book: Mapped[bool] = mapped_column(Boolean, default=False)
    last_check_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="watches")


class SlotSeen(Base):
    __tablename__ = "slots_seen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    provider_name: Mapped[str] = mapped_column(String(128))
    slot_hash: Mapped[str] = mapped_column(String(64), index=True)
    slot_datetime: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    center: Mapped[str | None] = mapped_column(String(256), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_notified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BookingAttempt(Base):
    __tablename__ = "booking_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    provider_name: Mapped[str] = mapped_column(String(128))
    slot_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32), default="started"
    )  # started | need_user_action | success | failed
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProviderSession(Base):
    __tablename__ = "provider_sessions"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    provider_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    cookies_encrypted: Mapped[bytes | None] = mapped_column(nullable=True)
    storage_state_encrypted: Mapped[bytes | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
