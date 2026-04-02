"""Add user_streaks and streak_milestones tables.

Revision ID: 006
Revises: 005
Create Date: 2026-03-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_streaks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True),
        sa.Column("current_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("longest_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_streak_date", sa.Date, nullable=True),
        sa.Column("today_spent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_bonus_earned", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_milestone_claimed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "streak_milestones",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("days_required", sa.Integer, nullable=False, unique=True, index=True),
        sa.Column("bonus_credits", sa.Integer, nullable=False),
        sa.Column("label", sa.String(128), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("streak_milestones")
    op.drop_table("user_streaks")
