"""Add last_spend_date to user_streaks to fix partial-day spend tracking.

Revision ID: 015
Revises: 014
"""
from alembic import op
import sqlalchemy as sa


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_streaks", sa.Column("last_spend_date", sa.Date, nullable=True))

    # Backfill: set last_spend_date = last_streak_date for existing rows
    op.execute("UPDATE user_streaks SET last_spend_date = last_streak_date WHERE last_streak_date IS NOT NULL")


def downgrade() -> None:
    op.drop_column("user_streaks", "last_spend_date")
