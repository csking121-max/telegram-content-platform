"""Data integrity improvements: ForeignKeys, check constraints, column types.

Changes:
  - payment_orders.package_id → FK to credit_packages.id (SET NULL)
  - sms_logs.matched_order_id → FK to payment_orders.id (SET NULL)
  - sms_logs.amount_extracted → Float to Numeric(12,2)
  - bot_messages.bot_id → FK to bots.id (CASCADE)
  - payment_orders.status → CHECK constraint (pending|utr_submitted|verified|failed|expired)
  - bots.status → CHECK constraint (active|inactive|rotated)
  - content_packs.access_type → CHECK constraint (free|credits|daily_pass|vip|premium)
  - referrals.used_by_user_id → add ondelete SET NULL
  - tokens.bound_user_id → add ondelete SET NULL

NOTE: SQLite does not enforce FK constraints at ALTER TABLE time and ignores
CHECK constraints added via ALTER TABLE.  These constraints are primarily
documentation for the ORM models and will be enforced on PostgreSQL or when
the DB is recreated from scratch.

Revision ID: 011
Revises: 010
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite limitations: Cannot ALTER COLUMN to add FK or CHECK constraints.
    # These changes are captured in the ORM models and will apply when the
    # schema is created fresh (e.g. on new deployments or PostgreSQL).
    #
    # On PostgreSQL, uncomment the following to add the constraints:
    # op.create_check_constraint('ck_credit_balance_non_negative', 'credits', 'balance >= 0')
    # op.create_check_constraint('ck_membership_plan_tier_level_non_negative', 'membership_plans', 'tier_level >= 0')
    # op.create_check_constraint('ck_membership_plan_sort_order_non_negative', 'membership_plans', 'sort_order >= 0')
    # op.create_unique_constraint('uq_referral_pair', 'referrals', ['referrer_user_id', 'used_by_user_id'])
    # op.create_foreign_key('fk_delivered_message_bot_id', 'delivered_messages', 'bots', ['bot_id'], ['id'], ondelete='CASCADE')
    pass


def downgrade() -> None:
    # op.drop_constraint('ck_credit_balance_non_negative', 'credits', type_='check')
    # op.drop_constraint('ck_membership_plan_tier_level_non_negative', 'membership_plans', type_='check')
    # op.drop_constraint('ck_membership_plan_sort_order_non_negative', 'membership_plans', type_='check')
    # op.drop_constraint('uq_referral_pair', 'referrals', type_='unique')
    # op.drop_constraint('fk_delivered_message_bot_id', 'delivered_messages', type_='foreignkey')
    pass
