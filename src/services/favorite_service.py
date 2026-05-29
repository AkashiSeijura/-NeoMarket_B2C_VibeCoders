from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.cart import Favorite
from src.schemas.catalog import CatalogProductCard, PaginatedCatalogProducts
from src.schemas.favorites import FavoriteResponse
from src.services.b2b_client import B2BClient
from src.services.catalog_service import _normalize_catalog_item
from src.services.errors import NotFoundError


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
