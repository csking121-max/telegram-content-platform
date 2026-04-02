"""Initial schema — all 12 tables.

Revision ID: 001
Revises:
Create Date: 2026-02-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger, unique=True, nullable=False, index=True),
        sa.Column("username", sa.String(255), nullable=True, index=True),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
    )

    # ── bots ─────────────────────────────────────────
    op.create_table(
        "bots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bot_username", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("bot_token", sa.String(255), nullable=False),
        sa.Column("webhook_secret", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── content_packs ────────────────────────────────
    op.create_table(
        "content_packs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.String(2048), nullable=True),
        sa.Column("access_type", sa.String(32), nullable=False, server_default="free"),
        sa.Column("credit_cost", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deletion_seconds", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── pack_items ───────────────────────────────────
    op.create_table(
        "pack_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pack_id", sa.Integer, sa.ForeignKey("content_packs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("storage_chat_id", sa.BigInteger, nullable=False),
        sa.Column("storage_message_id", sa.BigInteger, nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
    )

    # ── tokens ───────────────────────────────────────
    op.create_table(
        "tokens",
        sa.Column("token", sa.String(128), primary_key=True),
        sa.Column("pack_id", sa.Integer, sa.ForeignKey("content_packs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("single_use", sa.Boolean, server_default=sa.text("false")),
        sa.Column("bound_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("used_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── credits ──────────────────────────────────────
    op.create_table(
        "credits",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance", sa.Integer, nullable=False, server_default="0"),
    )

    # ── credit_history ───────────────────────────────
    op.create_table(
        "credit_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("change_amount", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── memberships ──────────────────────────────────
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("membership_type", sa.String(32), nullable=False, server_default="free"),
        sa.Column("start_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expiry_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── payments ─────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(64), nullable=False),
        sa.Column("reference", sa.String(512), unique=True, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── delivered_messages ───────────────────────────
    op.create_table(
        "delivered_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("bot_id", sa.Integer, sa.ForeignKey("bots.id"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger, nullable=False),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("delete_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── referrals ────────────────────────────────────
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("invite_code", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("referrer_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("used_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reward_granted", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── activity_logs ────────────────────────────────
    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("action", sa.String(128), nullable=False, index=True),
        sa.Column("payload", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("activity_logs")
    op.drop_table("referrals")
    op.drop_table("delivered_messages")
    op.drop_table("payments")
    op.drop_table("memberships")
    op.drop_table("credit_history")
    op.drop_table("credits")
    op.drop_table("tokens")
    op.drop_table("pack_items")
    op.drop_table("content_packs")
    op.drop_table("bots")
    op.drop_table("users")
