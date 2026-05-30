from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FavoriteResponse(BaseModel):
    product_id: uuid.UUID
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductSubscriptionRequest(BaseModel):
    notify_on: list[str] | None = None
    events: list[str] | None = Field(default=None, exclude=True)


class ProductSubscriptionResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    notify_on: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
