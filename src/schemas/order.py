from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderRequestItem(BaseModel):
    sku_id: uuid.UUID
    quantity: int = Field(ge=1)
    unit_price: int | None = Field(default=None, ge=0)


class OrderCreateRequest(BaseModel):
    address_id: uuid.UUID | None = None
    payment_method_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=1000)
    items_snapshot: list[OrderRequestItem] | None = None
    idempotency_key: uuid.UUID | None = None
    items: list[OrderRequestItem] | None = None
    delivery_address: str | None = None

    @model_validator(mode="after")
    def normalize_flow_items(self):
        if self.items_snapshot is None and self.items is not None:
            self.items_snapshot = self.items
        return self


class AddressResponse(BaseModel):
    id: uuid.UUID
    country: str = "RU"
    region: str | None = None
    city: str = ""
    street: str = ""
    building: str = ""
    apartment: str | None = None
    postal_code: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    is_default: bool = False
    comment: str | None = None
    created_at: datetime


class PaymentMethodResponse(BaseModel):
    id: uuid.UUID
    type: str = "CARD"
    card_last4: str | None = None
    card_brand: str | None = None
    is_default: bool = False
    created_at: datetime


class OrderItemRead(BaseModel):
    id: uuid.UUID | None = None
    sku_id: uuid.UUID
    product_id: uuid.UUID
    name: str
    product_title: str | None = None
    sku_name: str | None = None
    sku_code: str | None = None
    quantity: int
    unit_price: int
    line_total: int
    image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: uuid.UUID
    number: str | None = None
    buyer_id: uuid.UUID
    status: str
    status_history: list[dict] = []
    items: list[OrderItemRead]
    subtotal: int
    total_amount: int
    total: int
    delivery_cost: int = 0
    address: AddressResponse
    payment_method: PaymentMethodResponse | None = None
    delivery_address: str | None = None
    comment: str | None = None
    cancel_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None = None
    delivered_at: datetime | None = None
