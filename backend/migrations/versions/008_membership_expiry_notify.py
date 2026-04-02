"""add expiry_notified_at to memberships

Revision ID: 008
Revises: 007
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memberships") as batch_op:
        batch_op.add_column(
            sa.Column("expiry_notified_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("memberships") as batch_op:
        batch_op.drop_column("expiry_notified_at")
