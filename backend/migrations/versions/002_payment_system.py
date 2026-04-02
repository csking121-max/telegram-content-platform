"""Add payment system tables: membership_plans, upi_configs, sms_logs, payment_orders.

Revision ID: 002
Revises: 001
Create Date: 2025-01-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── membership_plans ─────────────────────────────
    op.create_table(
        "membership_plans",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("access_type", sa.String(32), nullable=False, server_default="vip"),
        sa.Column("price_inr", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration_days", sa.Integer, nullable=True),
        sa.Column("credit_reward", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── upi_configs ──────────────────────────────────
    op.create_table(
        "upi_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("upi_id", sa.String(255), unique=True, nullable=False),
        sa.Column("payee_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── sms_logs ─────────────────────────────────────
    op.create_table(
        "sms_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("sender", sa.String(128), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("utr_extracted", sa.String(64), nullable=True, index=True),
        sa.Column("amount_extracted", sa.Float, nullable=True),
        sa.Column("matched", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("matched_order_id", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── payment_orders ───────────────────────────────
    op.create_table(
        "payment_orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("plan_id", sa.Integer, sa.ForeignKey("membership_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("upi_id_used", sa.String(255), nullable=False),
        sa.Column("order_ref", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("utr_submitted", sa.String(64), nullable=True, index=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("payment_orders")
    op.drop_table("sms_logs")
    op.drop_table("upi_configs")
    op.drop_table("membership_plans")
