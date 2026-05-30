from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from src.models.cart import CartItem, EventIdempotencyKey


UNAVAILABLE_REASON_BY_EVENT = {
    "PRODUCT_BLOCKED": "PRODUCT_BLOCKED",
    "PRODUCT_DELETED": "PRODUCT_DELETED",
    "SKU_OUT_OF_STOCK": "OUT_OF_STOCK",
}


def handle_product_event(
    db: Session,
    *,
    idempotency_key: uuid.UUID,
    event_type: str,
    product_id: uuid.UUID,
    sku_ids: list[uuid.UUID],
) -> None:
    if db.get(EventIdempotencyKey, idempotency_key) is not None:
        return

    reason = UNAVAILABLE_REASON_BY_EVENT[event_type]
    db.add(
        EventIdempotencyKey(
            idempotency_key=idempotency_key,
            event_type=event_type,
            product_id=product_id,
        )
    )
    criteria = CartItem.sku_id.in_(sku_ids) if sku_ids else CartItem.product_id == product_id
    db.execute(update(CartItem).where(criteria).values(unavailable_reason=reason))
    db.commit()


def sku_ids_from_openapi_payload(event_type: str, payload: dict) -> list[uuid.UUID]:
    if event_type == "SKU_OUT_OF_STOCK":
        return [uuid.UUID(str(payload["sku_id"]))]
    if payload.get("sku_ids"):
        return [uuid.UUID(str(sku_id)) for sku_id in payload["sku_ids"]]
    return []
