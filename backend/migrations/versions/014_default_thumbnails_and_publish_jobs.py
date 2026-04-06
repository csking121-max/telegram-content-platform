"""Add default_thumbnails table and publish_jobs table.

Revision ID: 014
Revises: 013
"""
from alembic import op
import sqlalchemy as sa


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "default_thumbnails",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("file_id", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("mode", sa.String(16), nullable=False, server_default="solo"),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rate_per_minute", sa.Integer, nullable=False, server_default="2"),
        sa.Column("results", sa.Text, nullable=False, server_default="[]"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("publish_jobs")
    op.drop_table("default_thumbnails")
