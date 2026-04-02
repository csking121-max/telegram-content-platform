"""
Activity Logger — records user actions for auditing / analytics.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.activity_log import ActivityLog

logger = logging.getLogger(__name__)


class ActivityLogger:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        user_id: int,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ActivityLog:
        entry = ActivityLog(
            user_id=user_id,
            action=action,
            payload=json.dumps(payload) if payload else None,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def get_user_activity(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ActivityLog]:
        result = await self.db.execute(
            select(ActivityLog)
            .where(ActivityLog.user_id == user_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_recent(self, limit: int = 100) -> List[ActivityLog]:
        result = await self.db.execute(
            select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())