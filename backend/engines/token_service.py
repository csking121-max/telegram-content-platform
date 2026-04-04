"""
Token Service — creation, validation, and usage tracking of access tokens.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.content_pack import ContentPack
from backend.models.token import Token

logger = logging.getLogger(__name__)


class TokenService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Creation ─────────────────────────────────────

    async def create(
        self,
        pack_id: int,
        *,
        expires_in_hours: Optional[int] = None,
        single_use: bool = False,
        bound_user_id: Optional[int] = None,
    ) -> Token:
        """Generate a secure token linked to a content pack.
        expires_in_hours=None means no expiry (unlimited).
        """
        token_str = secrets.token_urlsafe(32)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
            if expires_in_hours is not None
            else None
        )

        token = Token(
            token=token_str,
            pack_id=pack_id,
            expires_at=expires_at,
            single_use=single_use,
            bound_user_id=bound_user_id,
        )
        self.db.add(token)
        await self.db.flush()
        logger.info("Created token=%s… for pack=%s", token_str[:8], pack_id)
        return token

    # ── Validation ───────────────────────────────────

    async def validate(self, token_str: str, user_id: Optional[int] = None) -> tuple[bool, str]:
        """
        Validate a token. Returns (is_valid, reason).
        """
        token = await self.get(token_str)
        if token is None:
            return False, "Token not found"

        if token.expires_at and datetime.now(timezone.utc) > token.expires_at:
            return False, "Token expired"

        if token.single_use and token.used_count > 0:
            return False, "Token already used"

        if token.bound_user_id and user_id and token.bound_user_id != user_id:
            return False, "Token bound to different user"

        return True, "Valid"

    # ── Usage ────────────────────────────────────────

    async def mark_used(self, token_str: str) -> Token:
        """Atomically increment used_count. For single-use tokens, only
        succeeds if used_count is still 0 (prevents concurrent reuse)."""
        token = await self.get(token_str)
        if token is None:
            raise ValueError("Token not found")

        if token.single_use:
            # Atomic CAS: only increment if still unused
            result = await self.db.execute(
                update(Token)
                .where(Token.token == token_str, Token.used_count == 0)
                .values(used_count=1)
            )
            if result.rowcount == 0:
                raise ValueError("Token already used")
            await self.db.refresh(token)
        else:
            token.used_count += 1
            await self.db.flush()
        return token

    # ── Lookups ──────────────────────────────────────

    async def get(self, token_str: str) -> Optional[Token]:
        result = await self.db.execute(select(Token).where(Token.token == token_str))
        return result.scalar_one_or_none()

    async def get_pack_for_token(self, token_str: str) -> Optional[ContentPack]:
        token = await self.get(token_str)
        if token is None:
            return None
        result = await self.db.execute(
            select(ContentPack).where(ContentPack.id == token.pack_id)
        )
        return result.scalar_one_or_none()