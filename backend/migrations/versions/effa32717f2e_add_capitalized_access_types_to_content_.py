"""Add capitalized access types to content pack constraint

Revision ID: effa32717f2e
Revises: 018
Create Date: 2026-04-23 01:24:19.510577
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'effa32717f2e'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old constraint
    op.drop_constraint('ck_content_pack_access_type', 'content_packs', type_='check')
    
    # Add the new constraint with capitalized access types
    op.create_check_constraint(
        'ck_content_pack_access_type',
        'content_packs',
        "access_type IN ('free', 'credits', 'credits_only', 'daily_pass', 'vip', 'premium', 'exclusive', 'Daily Pass', 'VIP', 'Premium', 'Exclusive')"
    )


def downgrade() -> None:
    # Drop the new constraint
    op.drop_constraint('ck_content_pack_access_type', 'content_packs', type_='check')
    
    # Add back the old constraint
    op.create_check_constraint(
        'ck_content_pack_access_type',
        'content_packs',
        "access_type IN ('free', 'credits', 'credits_only', 'daily_pass', 'vip', 'premium', 'exclusive')"
    )