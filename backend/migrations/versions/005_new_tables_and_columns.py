"""Add bot_messages, ad_watch_tokens, credit_packages tables and new columns.

New tables:
  - bot_messages (message tracking for auto-cleanup)
  - ad_watch_tokens (watch-ads-for-credits flow)
  - credit_packages (purchasable credit bundles)

New columns on existing tables:
  - bots.cleanup_hours
  - payment_orders.package_id
  - content_packs.credit_mode, content_packs.credit_per_item
  - membership_plans.tier_level

Revision ID: 005
Revises: 004
Create Date: 2025-07-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New tables ───────────────────────────────────────────

    op.create_table(
        "bot_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bot_id", sa.Integer, nullable=False, index=True),
        sa.Column("chat_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("message_id", sa.BigInteger, nullable=False),
        sa.Column("direction", sa.String(8), nullable=False, server_default="out"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ad_watch_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("ads_completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ads_required", sa.Integer, nullable=False, server_default="4"),
        sa.Column("activated", sa.Boolean, server_default=sa.text("false")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "credit_packages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True, server_default=""),
        sa.Column("credits", sa.Integer, nullable=False),
        sa.Column("price_inr", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── New columns on existing tables ───────────────────────

    with op.batch_alter_table("bots") as batch:
        batch.add_column(sa.Column("cleanup_hours", sa.Integer, nullable=False, server_default="0"))

    with op.batch_alter_table("payment_orders") as batch:
        batch.add_column(sa.Column("package_id", sa.Integer, nullable=True))

    with op.batch_alter_table("content_packs") as batch:
        batch.add_column(sa.Column("credit_mode", sa.String(16), nullable=False, server_default="per_item"))
        batch.add_column(sa.Column("credit_per_item", sa.Integer, nullable=False, server_default="1"))

    with op.batch_alter_table("membership_plans") as batch:
        batch.add_column(sa.Column("tier_level", sa.Integer, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("membership_plans") as batch:
        batch.drop_column("tier_level")

    with op.batch_alter_table("content_packs") as batch:
        batch.drop_column("credit_per_item")
        batch.drop_column("credit_mode")

    with op.batch_alter_table("payment_orders") as batch:
        batch.drop_column("package_id")

    with op.batch_alter_table("bots") as batch:
        batch.drop_column("cleanup_hours")

    op.drop_table("credit_packages")
    op.drop_table("ad_watch_tokens")
    op.drop_table("bot_messages")
