from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ProductEventType = Literal["PRODUCT_BLOCKED", "PRODUCT_DELETED", "SKU_OUT_OF_STOCK"]


class ProductEventRequest(BaseModel):
    idempotency_key: uuid.UUID
    event: ProductEventType
    product_id: uuid.UUID
    sku_ids: list[uuid.UUID] = Field(min_length=1)
    reason: str | None = None
    date: datetime


class B2BProductEventRequest(BaseModel):
    event_type: ProductEventType
    idempotency_key: uuid.UUID
    occurred_at: datetime
    payload: dict

    @model_validator(mode="after")
    def validate_payload(self) -> "B2BProductEventRequest":
        if "product_id" not in self.payload:
            raise ValueError("payload.product_id is required")
        if self.event_type == "SKU_OUT_OF_STOCK" and "sku_id" not in self.payload:
            raise ValueError("payload.sku_id is required")
        return self


class EventAcceptedResponse(BaseModel):
    accepted: bool = True
