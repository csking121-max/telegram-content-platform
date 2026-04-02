"""streak levels table and user_streaks columns

Revision ID: 007
Revises: 006
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New streak_levels table
    op.create_table(
        "streak_levels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("level", sa.Integer(), nullable=False, unique=True),
        sa.Column("streak_days_required", sa.Integer(), nullable=False, unique=True),
        sa.Column("bonus_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "membership_plan_id",
            sa.Integer(),
            sa.ForeignKey("membership_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("membership_duration_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(128), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_streak_levels_level", "streak_levels", ["level"])

    # New columns on user_streaks
    with op.batch_alter_table("user_streaks") as batch_op:
        batch_op.add_column(sa.Column("current_level", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("last_level_claimed", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("user_streaks") as batch_op:
        batch_op.drop_column("last_level_claimed")
        batch_op.drop_column("current_level")
    op.drop_index("ix_streak_levels_level", table_name="streak_levels")
    op.drop_table("streak_levels")
