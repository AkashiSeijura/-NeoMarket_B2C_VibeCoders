from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AddCartItemRequest(BaseModel):
    sku_id: uuid.UUID
    quantity: int


class UpdateCartItemRequest(BaseModel):
    quantity: int


class ImageRef(BaseModel):
    id: uuid.UUID | None = None
    url: str
    ordering: int = 0
    alt: str | None = None
    is_main: bool = True


class CartItemRead(BaseModel):
    sku_id: uuid.UUID
    product_id: uuid.UUID
    name: str
    quantity: int
    unit_price: int
    line_total: int
    available_quantity: int
    is_available: bool
    item_id: uuid.UUID | None = None
    product_title: str | None = None
    sku_name: str | None = None
    sku_code: str | None = None
    unit_price_at_add: int | None = None
    available_stock: int | None = None
    available: bool | None = None
    image: ImageRef | None = None
    image_url: str | None = None
    unavailable_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CartSummary(BaseModel):
    total_amount: int
    total_items: int
    total_quantity: int
    available_items: int
    unavailable_count: int = 0
    has_unavailable_items: bool
    checkout_ready: bool
    currency: str = "RUB"


class CheckoutItem(BaseModel):
    product_id: uuid.UUID
    sku_id: uuid.UUID
    quantity: int
    unit_price: int
    line_total: int


class CheckoutPayload(BaseModel):
    items: list[CheckoutItem]
    total_amount: int
    currency: str = "RUB"


class CartResponse(BaseModel):
    items: list[CartItemRead]
    items_count: int
    subtotal: int
    is_valid: bool
    id: uuid.UUID | None = None
    updated_at: datetime | None = None
    summary: CartSummary
    checkout_payload: CheckoutPayload


class CartMutationResponse(BaseModel):
    message: str
    item: CartItemRead
    summary: CartSummary


class CartValidationIssue(BaseModel):
    sku_id: uuid.UUID
    type: str
    message: str
    old_value: str | int | None = None
    new_value: str | int | None = None


class CartValidationResponse(BaseModel):
    is_valid: bool
    cart: CartResponse
    issues: list[CartValidationIssue]


class ErrorResponse(BaseModel):
    code: str
    message: str
