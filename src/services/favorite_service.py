from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.cart import Favorite, ProductSubscription
from src.schemas.catalog import CatalogProductCard, PaginatedCatalogProducts
from src.schemas.favorites import FavoriteResponse, ProductSubscriptionResponse
from src.services.b2b_client import B2BClient
from src.services.catalog_service import _normalize_catalog_item
from src.services.errors import DuplicateSubscriptionError, InvalidNotifyOnError, NotFoundError


ALLOWED_NOTIFY_ON = frozenset({"BACK_IN_STOCK", "PRICE_DROP"})
DEFAULT_NOTIFY_ON = ["BACK_IN_STOCK"]


def add_favorite(
    db: Session,
    user_id: uuid.UUID,
    product_id: uuid.UUID,
    b2b_client: B2BClient,
) -> tuple[FavoriteResponse, int]:
    _require_visible_product(b2b_client, product_id)
    existing = _find_favorite(db, user_id, product_id)
    if existing is not None:
        return FavoriteResponse.model_validate(existing), 200

    favorite = Favorite(user_id=user_id, product_id=product_id)
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return FavoriteResponse.model_validate(favorite), 201


def put_favorite(db: Session, user_id: uuid.UUID, product_id: uuid.UUID, b2b_client: B2BClient) -> None:
    add_favorite(db, user_id, product_id, b2b_client)


def delete_favorite(db: Session, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
    db.execute(delete(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id))
    db.commit()


def subscribe_to_product(
    db: Session,
    user_id: uuid.UUID,
    product_id: uuid.UUID,
    notify_on: list[str] | None,
    b2b_client: B2BClient,
) -> ProductSubscriptionResponse:
    _require_visible_product(b2b_client, product_id)
    normalized_notify_on = _normalize_notify_on(notify_on)
    if _find_subscription(db, user_id, product_id) is not None:
        raise DuplicateSubscriptionError("Subscription already exists")

    subscription = ProductSubscription(
        user_id=user_id,
        product_id=product_id,
        notify_on=normalized_notify_on,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return ProductSubscriptionResponse.model_validate(subscription)


def unsubscribe_from_product(db: Session, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
    db.execute(
        delete(ProductSubscription).where(
            ProductSubscription.user_id == user_id,
            ProductSubscription.product_id == product_id,
        )
    )
    db.commit()


def list_favorites(
    db: Session,
    user_id: uuid.UUID,
    b2b_client: B2BClient,
    *,
    limit: int,
    offset: int,
) -> PaginatedCatalogProducts:
    normalized_limit = min(max(limit, 1), 100)
    normalized_offset = max(offset, 0)
    favorites = list(
        db.scalars(
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.added_at.desc(), Favorite.id)
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
    )
    if not favorites:
        return PaginatedCatalogProducts(items=[], total_count=0, limit=normalized_limit, offset=normalized_offset)

    product_ids = [favorite.product_id for favorite in favorites]
    products = _visible_products_by_id(b2b_client, product_ids)
    items = [
        CatalogProductCard.model_validate(_normalize_catalog_item(products[product_id]))
        for product_id in product_ids
        if product_id in products
    ]
    return PaginatedCatalogProducts(
        items=items,
        total_count=len(items),
        limit=normalized_limit,
        offset=normalized_offset,
    )


def _find_favorite(db: Session, user_id: uuid.UUID, product_id: uuid.UUID) -> Favorite | None:
    return db.scalars(select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)).first()


def _find_subscription(db: Session, user_id: uuid.UUID, product_id: uuid.UUID) -> ProductSubscription | None:
    return db.scalars(
        select(ProductSubscription).where(
            ProductSubscription.user_id == user_id,
            ProductSubscription.product_id == product_id,
        )
    ).first()


def _normalize_notify_on(notify_on: list[str] | None) -> list[str]:
    values = notify_on if notify_on is not None else DEFAULT_NOTIFY_ON
    if not values:
        raise InvalidNotifyOnError("notify_on must contain at least one event")

    normalized = []
    for value in values:
        event = str(value).strip().upper()
        if event not in ALLOWED_NOTIFY_ON:
            raise InvalidNotifyOnError("notify_on contains unsupported event")
        if event not in normalized:
            normalized.append(event)
    return normalized


def _require_visible_product(b2b_client: B2BClient, product_id: uuid.UUID) -> dict:
    products = _visible_products_by_id(b2b_client, [product_id])
    product = products.get(product_id)
    if product is None:
        raise NotFoundError("Product not found")
    return product


def _visible_products_by_id(b2b_client: B2BClient, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    result = {}
    for product in b2b_client.fetch_products_by_ids(product_ids):
        parsed_id = _as_uuid(product.get("id"))
        if parsed_id is None or parsed_id not in product_ids or _is_hidden_product(product):
            continue
        result[parsed_id] = product
    return result


def _is_hidden_product(product: dict) -> bool:
    status = str(product.get("status") or "MODERATED")
    return (
        status != "MODERATED"
        or bool(product.get("deleted", product.get("is_deleted", False)))
        or bool(product.get("blocked", product.get("is_blocked", False)))
    )


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
