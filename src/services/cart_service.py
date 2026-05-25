from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from src.models.cart import CartItem
from src.schemas.cart import (
    CartItemRead,
    CartMutationResponse,
    CartResponse,
    CartSummary,
    CheckoutItem,
    CheckoutPayload,
)
from src.services.b2b_client import B2BClient, B2BSku
from src.services.errors import (
    CartItemNotFoundError,
    InsufficientStockError,
    InvalidQuantityError,
    SkuNotAvailableError,
    SkuNotFoundError,
)


@dataclass(frozen=True)
class CartIdentity:
    user_id: uuid.UUID | None = None
    session_id: str | None = None


def get_cart(db: Session, identity: CartIdentity, b2b_client: B2BClient) -> CartResponse:
    items = _list_items(db, identity)
    return _build_cart_response(items, b2b_client)


def get_cart_item(
    db: Session,
    identity: CartIdentity,
    item_id: uuid.UUID,
    b2b_client: B2BClient,
) -> CartItemRead:
    item = _get_owned_item(db, identity, item_id)
    enriched = _enrich_items([item], b2b_client)
    return enriched[0]


def add_item(
    db: Session,
    identity: CartIdentity,
    sku_id: uuid.UUID,
    quantity: int,
    b2b_client: B2BClient,
) -> tuple[CartMutationResponse, int]:
    _validate_quantity(quantity)
    sku = _require_orderable_sku(b2b_client, sku_id, quantity)
    existing = _find_item_by_sku(db, identity, sku_id)

    if existing is None:
        item = CartItem(
            user_id=identity.user_id,
            session_id=identity.session_id,
            sku_id=sku_id,
            product_id=sku.product_id,
            quantity=quantity,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        status_code = 201
        message = "Cart item created"
    else:
        new_quantity = existing.quantity + quantity
        _require_orderable_sku(b2b_client, sku_id, new_quantity)
        existing.quantity = new_quantity
        existing.product_id = sku.product_id
        db.commit()
        db.refresh(existing)
        item = existing
        status_code = 200
        message = "Cart item quantity increased"

    cart = _build_cart_response(_list_items(db, identity), b2b_client)
    enriched_item = next(read for read in cart.items if read.item_id == item.id)
    return CartMutationResponse(message=message, item=enriched_item, summary=cart.summary), status_code


def update_item(
    db: Session,
    identity: CartIdentity,
    item_id: uuid.UUID,
    quantity: int,
    b2b_client: B2BClient,
) -> CartMutationResponse:
    _validate_quantity(quantity)
    item = _get_owned_item(db, identity, item_id)
    sku = _require_orderable_sku(b2b_client, item.sku_id, quantity)

    item.quantity = quantity
    item.product_id = sku.product_id
    db.commit()
    db.refresh(item)

    cart = _build_cart_response(_list_items(db, identity), b2b_client)
    enriched_item = next(read for read in cart.items if read.item_id == item.id)
    return CartMutationResponse(message="Cart item quantity updated", item=enriched_item, summary=cart.summary)


def delete_item(db: Session, identity: CartIdentity, item_id: uuid.UUID) -> None:
    item = _get_owned_item(db, identity, item_id)
    db.delete(item)
    db.commit()


def clear_cart(db: Session, identity: CartIdentity) -> None:
    db.execute(delete(CartItem).where(*_identity_filters(identity)))
    db.commit()


def merge_guest_cart(
    db: Session,
    user_id: uuid.UUID,
    session_id: str,
    b2b_client: B2BClient,
) -> CartResponse:
    guest_identity = CartIdentity(session_id=session_id)
    auth_identity = CartIdentity(user_id=user_id)

    guest_items = _list_items(db, guest_identity)
    for guest_item in guest_items:
        auth_item = _find_item_by_sku(db, auth_identity, guest_item.sku_id)
        if auth_item is None:
            guest_item.user_id = user_id
            guest_item.session_id = None
        else:
            auth_item.quantity = max(auth_item.quantity, guest_item.quantity)
            if auth_item.product_id != guest_item.product_id:
                auth_item.product_id = guest_item.product_id
            db.delete(guest_item)

    db.execute(delete(CartItem).where(CartItem.session_id == session_id))
    db.commit()
    return get_cart(db, auth_identity, b2b_client)


def _build_cart_response(items: list[CartItem], b2b_client: B2BClient) -> CartResponse:
    enriched = _enrich_items(items, b2b_client)
    checkout_items = [
        CheckoutItem(
            product_id=item.product_id,
            sku_id=item.sku_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item in enriched
        if item.available and item.quantity <= item.available_stock
    ]
    total_amount = sum(item.line_total for item in checkout_items)
    total_quantity = sum(item.quantity for item in enriched)
    unavailable = [item for item in enriched if not item.available or item.quantity > item.available_stock]

    summary = CartSummary(
        total_amount=total_amount,
        total_items=len(enriched),
        total_quantity=total_quantity,
        available_items=len(enriched) - len([item for item in enriched if not item.available]),
        has_unavailable_items=bool(unavailable),
        checkout_ready=bool(enriched) and not unavailable,
    )
    return CartResponse(
        items=enriched,
        summary=summary,
        checkout_payload=CheckoutPayload(items=checkout_items, total_amount=total_amount),
    )


def _enrich_items(items: list[CartItem], b2b_client: B2BClient) -> list[CartItemRead]:
    sku_map = b2b_client.fetch_skus([item.sku_id for item in items])
    return [_to_read_model(item, sku_map.get(item.sku_id)) for item in items]


def _to_read_model(item: CartItem, sku: B2BSku | None) -> CartItemRead:
    if sku is None:
        return CartItemRead(
            item_id=item.id,
            sku_id=item.sku_id,
            product_id=item.product_id,
            product_title="",
            sku_name="",
            unit_price=0,
            quantity=item.quantity,
            available_stock=0,
            line_total=0,
            available=False,
            unavailable_reason="PRODUCT_DELISTED",
        )

    unavailable_reason = _unavailable_reason(sku)
    available = unavailable_reason is None
    line_total = sku.unit_price * item.quantity if available else 0

    return CartItemRead(
        item_id=item.id,
        sku_id=item.sku_id,
        product_id=sku.product_id,
        product_title=sku.product_title,
        sku_name=sku.sku_name,
        image_url=sku.image_url,
        unit_price=sku.unit_price,
        quantity=item.quantity,
        available_stock=sku.active_quantity,
        line_total=line_total,
        available=available,
        unavailable_reason=unavailable_reason,
    )


def _unavailable_reason(sku: B2BSku) -> str | None:
    if sku.product_status == "BLOCKED":
        return "PRODUCT_BLOCKED"
    if sku.product_status in {"DELETED", "DELISTED", "ON_MODERATION", "CREATED"}:
        return "PRODUCT_DELISTED"
    if not sku.sku_enabled:
        return "SKU_DISABLED"
    if sku.active_quantity <= 0:
        return "OUT_OF_STOCK"
    return None


def _require_orderable_sku(b2b_client: B2BClient, sku_id: uuid.UUID, quantity: int) -> B2BSku:
    sku = b2b_client.fetch_skus([sku_id]).get(sku_id)
    if sku is None:
        raise SkuNotFoundError("SKU does not exist")

    reason = _unavailable_reason(sku)
    if reason is not None:
        raise SkuNotAvailableError(f"SKU is not available: {reason}")
    if sku.active_quantity < quantity:
        raise InsufficientStockError(f"Cannot add {quantity}, only {sku.active_quantity} available")
    return sku


def _validate_quantity(quantity: int) -> None:
    if quantity < 1:
        raise InvalidQuantityError("Quantity must be at least 1")


def _list_items(db: Session, identity: CartIdentity) -> list[CartItem]:
    return list(
        db.scalars(
            select(CartItem)
            .where(*_identity_filters(identity))
            .order_by(CartItem.created_at, CartItem.id)
        )
    )


def _get_owned_item(db: Session, identity: CartIdentity, item_id: uuid.UUID) -> CartItem:
    item = db.scalars(select(CartItem).where(CartItem.id == item_id, *_identity_filters(identity))).first()
    if item is None:
        raise CartItemNotFoundError("Cart item not found")
    return item


def _find_item_by_sku(db: Session, identity: CartIdentity, sku_id: uuid.UUID) -> CartItem | None:
    return db.scalars(select(CartItem).where(CartItem.sku_id == sku_id, *_identity_filters(identity))).first()


def _identity_filters(identity: CartIdentity):
    if identity.user_id is not None:
        return (CartItem.user_id == identity.user_id,)
    return (CartItem.session_id == identity.session_id,)

