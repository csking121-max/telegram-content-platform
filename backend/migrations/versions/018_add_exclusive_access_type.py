"""Add exclusive access type to content packs.

Revision ID: 018
Revises: 017
"""
from alembic import op
import sqlalchemy as sa


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing constraint
    op.drop_constraint("ck_content_pack_access_type", "content_packs", type_="check")

    # Create new constraint with 'exclusive' added
    op.create_check_constraint(
        "ck_content_pack_access_type",
        "content_packs",
        "access_type IN ('free', 'credits', 'credits_only', 'daily_pass', 'vip', 'premium', 'exclusive')",
    )


def downgrade() -> None:
    # Drop the new constraint
    op.drop_constraint("ck_content_pack_access_type", "content_packs", type_="check")

    # Recreate the old constraint
    op.create_check_constraint(
        "ck_content_pack_access_type",
        "content_packs",
        "access_type IN ('free', 'credits', 'credits_only', 'daily_pass', 'vip', 'premium')",
    )