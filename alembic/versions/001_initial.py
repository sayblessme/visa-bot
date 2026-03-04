"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("center", sa.String(256), nullable=True),
        sa.Column("visa_type", sa.String(128), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("weekdays", sa.String(64), nullable=True),
        sa.Column("time_from", sa.Time(), nullable=True),
        sa.Column("time_to", sa.Time(), nullable=True),
        sa.Column("applicants_count", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "watches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "provider_name", sa.String(128), nullable=False, server_default="mock"
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_book", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "slots_seen",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=False),
        sa.Column("slot_hash", sa.String(64), nullable=False),
        sa.Column("slot_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("center", sa.String(256), nullable=True),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_slots_seen_slot_hash", "slots_seen", ["slot_hash"])

    op.create_table(
        "booking_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=False),
        sa.Column("slot_hash", sa.String(64), nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="started"
        ),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "provider_sessions",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=False),
        sa.Column("cookies_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("storage_state_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "provider_name"),
    )


def downgrade() -> None:
    op.drop_table("provider_sessions")
    op.drop_table("booking_attempts")
    op.drop_index("ix_slots_seen_slot_hash", "slots_seen")
    op.drop_table("slots_seen")
    op.drop_table("watches")
    op.drop_table("user_preferences")
    op.drop_table("users")
