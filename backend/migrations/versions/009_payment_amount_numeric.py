"""change payment_orders.amount from Float to Numeric(12,2)

Revision ID: 009
Revises: 008
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite doesn't enforce column types strictly, so this is mostly
    # a schema documentation change. For PostgreSQL this would be:
    # op.alter_column('payment_orders', 'amount', type_=sa.Numeric(12, 2))
    #
    # For SQLite we recreate the column via batch mode:
    with op.batch_alter_table("payment_orders") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Float(),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("payment_orders") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Numeric(12, 2),
            type_=sa.Float(),
            existing_nullable=False,
        )
