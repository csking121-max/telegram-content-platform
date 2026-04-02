"""Add credit_price and duration_hours to membership_plans.

Revision ID: 004
Revises: 003
Create Date: 2026-03-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("membership_plans") as batch:
        batch.add_column(sa.Column("credit_price", sa.Integer, nullable=False, server_default="0"))
        batch.add_column(sa.Column("duration_hours", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("membership_plans") as batch:
        batch.drop_column("duration_hours")
        batch.drop_column("credit_price")
