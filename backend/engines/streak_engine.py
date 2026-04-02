"""
Streak Engine — tracks daily credit spending streaks and awards milestone bonuses.

Flow:
  1. After each credit deduction, call `record_spend(user_id, amount)`
  2. Engine accumulates today_spent; when >= min_daily_spend, the day is counted
  3. Consecutive days build the streak counter
  4. When streak hits a milestone, bonus credits are auto-awarded
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user_streak import UserStreak
from backend.models.streak_milestone import StreakMilestone
from backend.models.streak_level import StreakLevel
from backend.models.credit import Credit
from backend.models.credit_history import CreditHistory
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)


class StreakEngine:
    """Stateless — instantiate per request with an async session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Public API ───────────────────────────────────

    async def record_spend(self, user_id: int, amount: int) -> dict | None:
        """
        Called after a credit deduction.
        Returns a dict with streak info if a milestone was just awarded, else None.
        """
        settings = PlatformSettingsService(self.db)
        enabled = (await settings.get("streak_enabled", "true")).lower() in ("true", "1", "yes")
        if not enabled:
            return None

        min_spend = await settings.get_int("streak_min_daily_spend", 5)
        today = datetime.now(timezone.utc).date()

        streak = await self._get_or_create(user_id)

        # Reset today_spent if it's a new day
        if streak.last_streak_date != today:
            # Check if yesterday was a streak day (consecutive)
            yesterday = today - timedelta(days=1)
            if streak.last_streak_date == yesterday:
                # Yesterday was tracked — streak continues
                # (streak was already advanced when yesterday qualified)
                pass
            elif streak.last_streak_date and streak.last_streak_date < yesterday:
                # Missed a day — streak resets, but only if the last day was fully qualified
                streak.current_streak = 0
                streak.last_milestone_claimed = 0

            streak.today_spent = 0

        # Add today's spend
        streak.today_spent += amount

        # Check if today now qualifies
        if streak.today_spent >= min_spend and streak.last_streak_date != today:
            # This is the qualifying spend for today
            streak.current_streak += 1
            streak.last_streak_date = today
            if streak.current_streak > streak.longest_streak:
                streak.longest_streak = streak.current_streak
            logger.info(
                "Streak day! user=%s streak=%s today_spent=%s",
                user_id, streak.current_streak, streak.today_spent,
            )

            # Check for milestone bonus
            milestone = await self._check_milestone(streak)
            if milestone:
                await self._award_bonus(user_id, streak, milestone)

            # Check for level-up
            level_info = await self._check_level_up(user_id, streak)

            await self.db.flush()

            result_info: dict | None = None
            if milestone:
                result_info = {
                    "current_streak": streak.current_streak,
                    "milestone_days": milestone.days_required,
                    "bonus_credits": milestone.bonus_credits,
                    "milestone_label": milestone.label,
                }
            if level_info:
                if result_info is None:
                    result_info = {"current_streak": streak.current_streak}
                result_info["level_up"] = level_info
            return result_info

        await self.db.flush()
        return None

    async def get_user_streak(self, user_id: int) -> dict:
        """Get streak info for a user's profile."""
        settings = PlatformSettingsService(self.db)
        enabled = (await settings.get("streak_enabled", "true")).lower() in ("true", "1", "yes")
        min_spend = await settings.get_int("streak_min_daily_spend", 5)

        streak = await self._get_or_create(user_id)
        today = datetime.now(timezone.utc).date()

        # Determine if streak is still alive
        current = streak.current_streak
        if streak.last_streak_date and streak.last_streak_date < today - timedelta(days=1):
            current = 0  # Expired (display only, don't mutate here)

        today_progress = streak.today_spent if streak.last_streak_date == today or streak.today_spent > 0 else 0
        if streak.last_streak_date != today:
            today_progress = streak.today_spent  # might be partial

        # Recalculate — if last_streak_date is today, today_spent is finalized for display
        today_qualified = streak.last_streak_date == today

        # Next milestone
        next_milestone = await self._next_milestone(current)

        # Level info
        level_info = await self._compute_level(current, streak)
        next_level = await self._next_level(current)

        return {
            "enabled": enabled,
            "current_streak": current,
            "longest_streak": streak.longest_streak,
            "today_spent": streak.today_spent if streak.last_streak_date == today else 0,
            "today_qualified": today_qualified,
            "min_daily_spend": min_spend,
            "total_bonus_earned": streak.total_bonus_earned,
            "current_level": level_info,
            "next_level": {
                "level": next_level.level,
                "streak_days_required": next_level.streak_days_required,
                "label": next_level.label,
                "bonus_credits": next_level.bonus_credits,
                "has_membership": next_level.membership_plan_id is not None,
                "days_remaining": max(0, next_level.streak_days_required - current),
            } if next_level else None,
            "next_milestone": {
                "days_required": next_milestone.days_required,
                "bonus_credits": next_milestone.bonus_credits,
                "label": next_milestone.label,
                "days_remaining": max(0, next_milestone.days_required - current),
            } if next_milestone else None,
        }

    async def get_all_streaks(self, skip: int = 0, limit: int = 50) -> list[dict]:
        """Admin: get all user streaks with user info."""
        from backend.models.user import User
        result = await self.db.execute(
            select(UserStreak, User.telegram_id, User.username)
            .join(User, UserStreak.user_id == User.id)
            .order_by(UserStreak.current_streak.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = result.all()
        return [
            {
                "user_id": s.user_id,
                "telegram_id": tg_id,
                "username": uname,
                "current_streak": s.current_streak,
                "longest_streak": s.longest_streak,
                "today_spent": s.today_spent,
                "last_streak_date": s.last_streak_date.isoformat() if s.last_streak_date else None,
                "total_bonus_earned": s.total_bonus_earned,
                "last_milestone_claimed": s.last_milestone_claimed,
                "current_level": s.current_level,
            }
            for s, tg_id, uname in rows
        ]

    async def reset_user_streak(self, user_id: int) -> None:
        """Admin: reset a user's streak to 0."""
        streak = await self._get_or_create(user_id)
        streak.current_streak = 0
        streak.today_spent = 0
        streak.last_streak_date = None
        streak.last_milestone_claimed = 0
        streak.current_level = 0
        streak.last_level_claimed = 0
        await self.db.flush()

    # ── Milestones CRUD (for admin) ──────────────────

    async def list_milestones(self) -> list[StreakMilestone]:
        result = await self.db.execute(
            select(StreakMilestone).order_by(StreakMilestone.days_required)
        )
        return list(result.scalars().all())

    async def create_milestone(
        self, days_required: int, bonus_credits: int, label: str = "", is_active: bool = True,
    ) -> StreakMilestone:
        m = StreakMilestone(
            days_required=days_required,
            bonus_credits=bonus_credits,
            label=label or f"{days_required}-day streak",
            is_active=is_active,
        )
        self.db.add(m)
        await self.db.flush()
        return m

    async def update_milestone(self, milestone_id: int, **kwargs) -> StreakMilestone | None:
        result = await self.db.execute(
            select(StreakMilestone).where(StreakMilestone.id == milestone_id)
        )
        m = result.scalar_one_or_none()
        if not m:
            return None
        for k, v in kwargs.items():
            if hasattr(m, k) and v is not None:
                setattr(m, k, v)
        await self.db.flush()
        return m

    async def delete_milestone(self, milestone_id: int) -> bool:
        result = await self.db.execute(
            select(StreakMilestone).where(StreakMilestone.id == milestone_id)
        )
        m = result.scalar_one_or_none()
        if not m:
            return False
        await self.db.delete(m)
        await self.db.flush()
        return True

    # ── Internal ─────────────────────────────────────

    async def _get_or_create(self, user_id: int) -> UserStreak:
        result = await self.db.execute(
            select(UserStreak).where(UserStreak.user_id == user_id)
        )
        streak = result.scalar_one_or_none()
        if not streak:
            streak = UserStreak(user_id=user_id)
            self.db.add(streak)
            await self.db.flush()
        return streak

    async def _check_milestone(self, streak: UserStreak) -> StreakMilestone | None:
        """Find the highest active milestone the user just reached but hasn't claimed."""
        result = await self.db.execute(
            select(StreakMilestone)
            .where(
                StreakMilestone.is_active == True,
                StreakMilestone.days_required <= streak.current_streak,
                StreakMilestone.days_required > streak.last_milestone_claimed,
            )
            .order_by(StreakMilestone.days_required.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _next_milestone(self, current_streak: int) -> StreakMilestone | None:
        """Find the next unclaimed milestone ahead of the current streak."""
        result = await self.db.execute(
            select(StreakMilestone)
            .where(
                StreakMilestone.is_active == True,
                StreakMilestone.days_required > current_streak,
            )
            .order_by(StreakMilestone.days_required)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _award_bonus(
        self, user_id: int, streak: UserStreak, milestone: StreakMilestone,
    ) -> None:
        """Award milestone bonus credits to user."""
        # Add credits
        result = await self.db.execute(select(Credit).where(Credit.user_id == user_id))
        credit = result.scalar_one_or_none()
        if credit:
            credit.balance += milestone.bonus_credits
        else:
            credit = Credit(user_id=user_id, balance=milestone.bonus_credits)
            self.db.add(credit)

        # Record in history
        reason = f"streak_bonus:{milestone.days_required}d:{milestone.bonus_credits}c"
        self.db.add(CreditHistory(
            user_id=user_id,
            change_amount=milestone.bonus_credits,
            reason=reason,
        ))

        # Update streak tracking
        streak.last_milestone_claimed = milestone.days_required
        streak.total_bonus_earned += milestone.bonus_credits

        logger.info(
            "Streak milestone! user=%s days=%s bonus=%s",
            user_id, milestone.days_required, milestone.bonus_credits,
        )

    # ── Level CRUD (for admin) ───────────────────────

    async def list_levels(self) -> list[StreakLevel]:
        result = await self.db.execute(
            select(StreakLevel).order_by(StreakLevel.level)
        )
        return list(result.scalars().all())

    async def create_level(
        self,
        level: int,
        streak_days_required: int,
        bonus_credits: int = 0,
        membership_plan_id: int | None = None,
        membership_duration_days: int = 0,
        label: str = "",
        is_active: bool = True,
    ) -> StreakLevel:
        lv = StreakLevel(
            level=level,
            streak_days_required=streak_days_required,
            bonus_credits=bonus_credits,
            membership_plan_id=membership_plan_id,
            membership_duration_days=membership_duration_days,
            label=label or f"Level {level}",
            is_active=is_active,
        )
        self.db.add(lv)
        await self.db.flush()
        return lv

    async def update_level(self, level_id: int, **kwargs) -> StreakLevel | None:
        result = await self.db.execute(
            select(StreakLevel).where(StreakLevel.id == level_id)
        )
        lv = result.scalar_one_or_none()
        if not lv:
            return None
        for k, v in kwargs.items():
            if hasattr(lv, k) and v is not None:
                setattr(lv, k, v)
        await self.db.flush()
        return lv

    async def delete_level(self, level_id: int) -> bool:
        result = await self.db.execute(
            select(StreakLevel).where(StreakLevel.id == level_id)
        )
        lv = result.scalar_one_or_none()
        if not lv:
            return False
        await self.db.delete(lv)
        await self.db.flush()
        return True

    # ── Internal — Levels ────────────────────────────

    async def _compute_level(self, current_streak: int, streak: UserStreak) -> dict | None:
        """Compute the user's current level based on streak count."""
        result = await self.db.execute(
            select(StreakLevel)
            .where(
                StreakLevel.is_active == True,
                StreakLevel.streak_days_required <= current_streak,
            )
            .order_by(StreakLevel.level.desc())
            .limit(1)
        )
        lv = result.scalar_one_or_none()
        if not lv:
            return None
        return {
            "level": lv.level,
            "label": lv.label,
            "streak_days_required": lv.streak_days_required,
        }

    async def _next_level(self, current_streak: int) -> StreakLevel | None:
        """Find the next level beyond current streak."""
        result = await self.db.execute(
            select(StreakLevel)
            .where(
                StreakLevel.is_active == True,
                StreakLevel.streak_days_required > current_streak,
            )
            .order_by(StreakLevel.streak_days_required)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _check_level_up(self, user_id: int, streak: UserStreak) -> dict | None:
        """Check if user qualifies for a new level and award rewards."""
        result = await self.db.execute(
            select(StreakLevel)
            .where(
                StreakLevel.is_active == True,
                StreakLevel.streak_days_required <= streak.current_streak,
                StreakLevel.level > streak.last_level_claimed,
            )
            .order_by(StreakLevel.level.desc())
            .limit(1)
        )
        lv = result.scalar_one_or_none()
        if not lv:
            return None

        # Award bonus credits if any
        if lv.bonus_credits > 0:
            cr_result = await self.db.execute(select(Credit).where(Credit.user_id == user_id))
            credit = cr_result.scalar_one_or_none()
            if credit:
                credit.balance += lv.bonus_credits
            else:
                credit = Credit(user_id=user_id, balance=lv.bonus_credits)
                self.db.add(credit)

            self.db.add(CreditHistory(
                user_id=user_id,
                change_amount=lv.bonus_credits,
                reason=f"level_up:{lv.level}:{lv.bonus_credits}c",
            ))
            streak.total_bonus_earned += lv.bonus_credits

        # Grant membership if configured
        membership_granted = None
        if lv.membership_plan_id and lv.membership_duration_days > 0:
            from backend.models.membership_plan import MembershipPlan
            from backend.engines.membership_engine import MembershipEngine
            from datetime import datetime, timezone, timedelta

            plan_result = await self.db.execute(
                select(MembershipPlan).where(MembershipPlan.id == lv.membership_plan_id)
            )
            plan = plan_result.scalar_one_or_none()
            if plan:
                mem_engine = MembershipEngine(self.db)
                expiry = datetime.now(timezone.utc) + timedelta(days=lv.membership_duration_days)
                await mem_engine.grant(
                    user_id=user_id,
                    membership_type=plan.access_type,
                    expiry_at=expiry,
                )
                membership_granted = {
                    "plan_name": plan.display_name,
                    "access_type": plan.access_type,
                    "duration_days": lv.membership_duration_days,
                }

        # Update streak tracking
        streak.current_level = lv.level
        streak.last_level_claimed = lv.level

        logger.info(
            "Level up! user=%s level=%s credits=%s membership=%s",
            user_id, lv.level, lv.bonus_credits,
            membership_granted["plan_name"] if membership_granted else "none",
        )

        return {
            "level": lv.level,
            "label": lv.label,
            "bonus_credits": lv.bonus_credits,
            "membership": membership_granted,
        }
