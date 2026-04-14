"""Add bug_reports and tutorials tables.

Revision ID: 017
Revises: 016
"""
from alembic import op
import sqlalchemy as sa


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bug_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("report", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "tutorials",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("question", sa.String(512), nullable=False),
        sa.Column("storage_chat_id", sa.BigInteger, nullable=False),
        sa.Column("storage_message_id", sa.BigInteger, nullable=False),
        sa.Column("file_id", sa.String(256), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("tutorials")
    op.drop_table("bug_reports")
