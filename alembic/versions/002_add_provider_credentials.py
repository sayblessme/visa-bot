"""Add provider credentials to user_preferences

Revision ID: 002
Revises: 001
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("provider_email", sa.String(256), nullable=True))
    op.add_column("user_preferences", sa.Column("provider_password_encrypted", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_preferences", "provider_password_encrypted")
    op.drop_column("user_preferences", "provider_email")
