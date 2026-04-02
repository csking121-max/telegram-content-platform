"""Schemas for the ad-watch flow."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AdWatchStart(BaseModel):
    telegram_id: int
    bot_username: str = ""


class AdWatchStartResponse(BaseModel):
    token: str
    ads_required: int
    ad_page_url: str
    free_hours: int = 12


class AdStepComplete(BaseModel):
    token: str
    step: int
    bot_username: str = ""


class AdStepCompleteResponse(BaseModel):
    step_completed: int
    ads_remaining: int
    all_done: bool
    redirect_deep_link: str | None = None


class AdWatchActivate(BaseModel):
    token: str
    telegram_id: int


class AdWatchActivateResponse(BaseModel):
    activated: bool
    expires_at: str | None = None
    message: str


class AdWatchTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    token: str
    ads_completed: int
    ads_required: int
    activated: bool
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    used: bool
    created_at: datetime
