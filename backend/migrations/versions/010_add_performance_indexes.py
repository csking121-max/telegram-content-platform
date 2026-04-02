"""Add performance indexes for frequently queried columns.

Indexes added:
  - delivered_messages.delete_at  (deletion worker scans by delete_at)
  - payment_orders.status         (filtered by status in many queries)
  - content_packs.access_type     (access control checks by access_type)
  - platform_settings.category    (admin UI filters by category)

Revision ID: 010
Revises: 009
Create Date: 2026-03-09
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_delivered_messages_delete_at", "delivered_messages", ["delete_at"])
    op.create_index("ix_payment_orders_status", "payment_orders", ["status"])
    op.create_index("ix_content_packs_access_type", "content_packs", ["access_type"])
    op.create_index("ix_platform_settings_category", "platform_settings", ["category"])


def downgrade() -> None:
    op.drop_index("ix_platform_settings_category", "platform_settings")
    op.drop_index("ix_content_packs_access_type", "content_packs")
    op.drop_index("ix_payment_orders_status", "payment_orders")
    op.drop_index("ix_delivered_messages_delete_at", "delivered_messages")
