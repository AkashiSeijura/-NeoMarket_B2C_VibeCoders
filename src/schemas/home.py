from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BannerRead(BaseModel):
    id: uuid.UUID
    title: str
    image_url: str
    link: str
    priority: int


class BannerResponse(BaseModel):
    items: list[BannerRead]
    total_count: int


class OpenAPIBanner(BaseModel):
    id: uuid.UUID
    title: str | None = None
    image_url: str
    link: str
    ordering: int | None = None
    active_from: datetime | None = None
    active_to: datetime | None = None


class BannerEventIn(BaseModel):
    banner_id: uuid.UUID
    event: Literal["impression", "click"]
    timestamp: datetime | None = None


class BannerEventsRequest(BaseModel):
    events: list[BannerEventIn] = Field(default_factory=list)


class BannerEventsResponse(BaseModel):
    accepted_count: int
