"""Add custom_credits column to payment_orders for custom-amount credit purchases.

Revision ID: 012
Revises: 011
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_orders",
        sa.Column("custom_credits", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_orders", "custom_credits")
