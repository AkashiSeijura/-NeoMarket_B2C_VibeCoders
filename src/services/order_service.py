from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.models.cart import CartItem
from src.models.order import Order, OrderItem
from src.schemas.order import (
    AddressResponse,
    OrderCreateRequest,
    OrderItemRead,
    OrderRequestItem,
    OrderResponse,
    PaymentMethodResponse,
)
from src.services.b2b_client import B2BClient, B2BSku
from src.services.errors import (
    B2BCheckoutUnavailableError,
    B2BUnavailableError,
    EmptyOrderError,
    IdempotencyConflictError,
    ReserveFailedError,
)


def checkout(
    db: Session,
    buyer_id: uuid.UUID,
    payload: OrderCreateRequest,
    idempotency_key: uuid.UUID,
    b2b_client: B2BClient,
) -> OrderResponse:
    requested_items = _requested_items(db, buyer_id, payload)
    request_hash = _request_hash(buyer_id, payload, idempotency_key, requested_items)

    existing = _get_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError("Idempotency key was already used with a different request")
        return _to_response(existing)

    try:
        sku_map = b2b_client.fetch_skus([item.sku_id for item in requested_items])
        _validate_skus(requested_items, sku_map)
        b2b_client.reserve(
            idempotency_key,
            [{"sku_id": str(item.sku_id), "quantity": item.quantity} for item in requested_items],
        )
    except B2BUnavailableError as exc:
        raise B2BCheckoutUnavailableError("B2B service unavailable") from exc

    order = _build_order(buyer_id, payload, idempotency_key, request_hash, requested_items, sku_map)
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _get_by_idempotency_key(db, idempotency_key)
        if existing is not None and existing.request_hash == request_hash:
            return _to_response(existing)
        raise IdempotencyConflictError("Idempotency key was already used with a different request")

    db.refresh(order)
    return _to_response(order)


def _requested_items(db: Session, buyer_id: uuid.UUID, payload: OrderCreateRequest) -> list[OrderRequestItem]:
    if payload.items_snapshot:
        items = payload.items_snapshot
    else:
        cart_items = list(
            db.scalars(
                select(CartItem).where(CartItem.user_id == buyer_id).order_by(CartItem.created_at, CartItem.id)
            )
        )
        items = [OrderRequestItem(sku_id=item.sku_id, quantity=item.quantity) for item in cart_items]

    if not items:
        raise EmptyOrderError("Order items must not be empty")
    return _merge_duplicate_items(items)


def _merge_duplicate_items(items: list[OrderRequestItem]) -> list[OrderRequestItem]:
    merged: dict[uuid.UUID, int] = {}
    prices: dict[uuid.UUID, int | None] = {}
    for item in items:
        merged[item.sku_id] = merged.get(item.sku_id, 0) + item.quantity
        prices.setdefault(item.sku_id, item.unit_price)
    return [
        OrderRequestItem(sku_id=sku_id, quantity=quantity, unit_price=prices.get(sku_id))
        for sku_id, quantity in sorted(merged.items(), key=lambda pair: str(pair[0]))
    ]


def _request_hash(
    buyer_id: uuid.UUID,
    payload: OrderCreateRequest,
    idempotency_key: uuid.UUID,
    items: list[OrderRequestItem],
) -> str:
    raw = {
        "buyer_id": str(buyer_id),
        "idempotency_key": str(idempotency_key),
        "address_id": str(payload.address_id) if payload.address_id else None,
        "payment_method_id": str(payload.payment_method_id) if payload.payment_method_id else None,
        "delivery_address": payload.delivery_address,
        "comment": payload.comment,
        "items": [
            {"sku_id": str(item.sku_id), "quantity": item.quantity, "unit_price": item.unit_price}
            for item in items
        ],
    }
    return hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _get_by_idempotency_key(db: Session, idempotency_key: uuid.UUID) -> Order | None:
    return db.scalars(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.idempotency_key == idempotency_key)
    ).first()


def _validate_skus(items: list[OrderRequestItem], sku_map: dict[uuid.UUID, B2BSku]) -> None:
    failed_items = []
    for item in items:
        sku = sku_map.get(item.sku_id)
        if sku is None:
            failed_items.append({"sku_id": str(item.sku_id), "reason": "SKU_NOT_FOUND"})
            continue
        reason = _unavailable_reason(sku)
        if reason is not None:
            failed_items.append({"sku_id": str(item.sku_id), "reason": reason})
            continue
        if sku.active_quantity < item.quantity:
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "reason": "INSUFFICIENT_STOCK",
                    "requested": item.quantity,
                    "available": sku.active_quantity,
                }
            )

    if failed_items:
        raise ReserveFailedError(failed_items=failed_items)


def _unavailable_reason(sku: B2BSku) -> str | None:
    if sku.product_status in {"BLOCKED", "HARD_BLOCKED"}:
        return "PRODUCT_BLOCKED"
    if sku.product_status == "DELETED":
        return "PRODUCT_DELETED"
    if sku.product_status in {"ON_MODERATION", "EDITED", "CREATED"}:
        return "ON_MODERATION"
    if not sku.sku_enabled:
        return "SKU_DISABLED"
    return None


def _build_order(
    buyer_id: uuid.UUID,
    payload: OrderCreateRequest,
    idempotency_key: uuid.UUID,
    request_hash: str,
    items: list[OrderRequestItem],
    sku_map: dict[uuid.UUID, B2BSku],
) -> Order:
    order_items = []
    subtotal = 0
    for item in items:
        sku = sku_map[item.sku_id]
        line_total = sku.unit_price * item.quantity
        subtotal += line_total
        order_items.append(
            OrderItem(
                sku_id=sku.id,
                product_id=sku.product_id,
                product_title=sku.product_title,
                sku_name=sku.sku_name,
                quantity=item.quantity,
                unit_price=sku.unit_price,
                line_total=line_total,
                image_url=sku.image_url,
            )
        )

    return Order(
        buyer_id=buyer_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="PAID",
        subtotal=subtotal,
        delivery_cost=0,
        total=subtotal,
        address_id=payload.address_id,
        payment_method_id=payload.payment_method_id,
        delivery_address=payload.delivery_address,
        comment=payload.comment,
        items=order_items,
    )


def _to_response(order: Order) -> OrderResponse:
    address_id = order.address_id or order.id
    return OrderResponse(
        id=order.id,
        number=f"NM-{str(order.id)[:8]}",
        buyer_id=order.buyer_id,
        status=order.status,
        items=[
            OrderItemRead(
                id=item.id,
                sku_id=item.sku_id,
                product_id=item.product_id,
                name=" ".join(part for part in [item.product_title, item.sku_name] if part),
                product_title=item.product_title,
                sku_name=item.sku_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                image_url=item.image_url,
            )
            for item in sorted(order.items, key=lambda item: str(item.sku_id))
        ],
        subtotal=order.subtotal,
        total_amount=order.total,
        total=order.total,
        delivery_cost=order.delivery_cost,
        address=AddressResponse(
            id=address_id,
            comment=order.delivery_address,
            created_at=order.created_at,
        ),
        payment_method=_payment_method(order),
        delivery_address=order.delivery_address,
        comment=order.comment,
        created_at=order.created_at,
        updated_at=order.updated_at,
        paid_at=order.created_at,
    )


def _payment_method(order: Order) -> PaymentMethodResponse | None:
    if order.payment_method_id is None:
        return None
    return PaymentMethodResponse(id=order.payment_method_id, created_at=order.created_at)
