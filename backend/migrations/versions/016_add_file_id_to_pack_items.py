"""Add file_id column to pack_items for direct download without forwarding.

Revision ID: 016
Revises: 015
"""
from alembic import op
import sqlalchemy as sa


revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pack_items", sa.Column("file_id", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("pack_items", "file_id")
