from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class AddCartItemRequest(BaseModel):
    sku_id: uuid.UUID
    quantity: int


class UpdateCartItemRequest(BaseModel):
    quantity: int


class CartItemRead(BaseModel):
    item_id: uuid.UUID
    sku_id: uuid.UUID
    product_id: uuid.UUID
    product_title: str
    sku_name: str
    image_url: str | None = None
    unit_price: int
    quantity: int
    available_stock: int
    line_total: int
    available: bool
    unavailable_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CartSummary(BaseModel):
    total_amount: int
    total_items: int
    total_quantity: int
    available_items: int
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
    summary: CartSummary
    checkout_payload: CheckoutPayload


class CartMutationResponse(BaseModel):
    message: str
    item: CartItemRead
    summary: CartSummary


class ErrorResponse(BaseModel):
    code: str
    message: str

