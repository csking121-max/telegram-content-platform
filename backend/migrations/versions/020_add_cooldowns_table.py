"""Add cooldowns table for link access rate limiting.

Revision ID: 020
Revises: effa32717f2e
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "effa32717f2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cooldowns",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=False, index=True),
        sa.Column("exceeded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("access_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reason", sa.String(256), nullable=True),
    )
    # Add foreign key constraint to users table
    op.create_foreign_key(
        "fk_cooldowns_user_id",
        "cooldowns",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_cooldowns_user_id", "cooldowns", type_="foreignkey")
    op.drop_table("cooldowns")
