"""Add platform_settings table.

Revision ID: 003
Revises: 002
Create Date: 2026-03-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("value", sa.Text, nullable=False, server_default=""),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("category", sa.String(64), nullable=False, server_default="general"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
