"""Add thumbnail_file_id column to content_packs.

Revision ID: 013
Revises: 012
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_packs",
        sa.Column("thumbnail_file_id", sa.String(256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_packs", "thumbnail_file_id")
