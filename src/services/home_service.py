from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.models.base import utcnow
from src.models.home import Banner, BannerEvent, Collection, CollectionProduct
from src.schemas.catalog import CatalogProductCard
from src.schemas.home import (
    BannerEventIn,
    BannerRead,
    BannerResponse,
    CollectionProductsResponse,
    CollectionRead,
    CollectionsMetadata,
    CollectionsResponse,
    OpenAPIBanner,
    OpenAPICollection,
)
from src.services.b2b_client import B2BClient
from src.services.catalog_service import is_hidden_catalog_product, normalize_catalog_product_card
from src.services.errors import BannerNotFoundError, EmptyEventsError
from src.services.errors import NotFoundError


def list_active_banners(db: Session) -> BannerResponse:
    banners = _active_banner_rows(db)
    items = [
        BannerRead(
            id=banner.id,
            title=banner.title,
            image_url=banner.image_url,
            link=banner.link,
            priority=banner.priority,
        )
        for banner in banners
    ]
    return BannerResponse(items=items, total_count=len(items))


def list_active_openapi_banners(db: Session) -> list[OpenAPIBanner]:
    return [
        OpenAPIBanner(
            id=banner.id,
            title=banner.title,
            image_url=banner.image_url,
            link=banner.link,
            ordering=banner.priority,
            active_from=banner.start_at,
            active_to=banner.end_at,
        )
        for banner in _active_banner_rows(db)
    ]


def list_active_collections(db: Session, *, limit: int, offset: int) -> CollectionsResponse:
    normalized_limit = _clamp(limit, 1, 100)
    normalized_offset = max(offset, 0)
    total_count = db.scalar(select(func.count()).select_from(_active_collections_subquery())) or 0
    stmt = _active_collections_stmt().limit(normalized_limit).offset(normalized_offset)
    collections = [
        CollectionRead(
            id=collection.id,
            title=collection.title,
            description=collection.description,
            cover_image_url=collection.cover_image_url,
            target_url=collection.target_url,
            priority=collection.priority,
        )
        for collection in db.scalars(stmt).all()
    ]
    return CollectionsResponse(
        collections=collections,
        metadata=CollectionsMetadata(
            total_count=total_count,
            limit=normalized_limit,
            offset=normalized_offset,
        ),
    )


def list_active_openapi_collections(db: Session, b2b_client: B2BClient) -> list[OpenAPICollection]:
    rows = db.scalars(_active_collections_stmt()).all()
    return [
        OpenAPICollection(
            id=collection.id,
            name=collection.title,
            description=collection.description,
            products=_collection_products(db, b2b_client, collection, limit=100, offset=0).items,
        )
        for collection in rows
    ]


def get_collection_products(
    db: Session,
    b2b_client: B2BClient,
    collection_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> CollectionProductsResponse:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise NotFoundError("Collection not found")
    return _collection_products(
        db,
        b2b_client,
        collection,
        limit=_clamp(limit, 1, 100),
        offset=max(offset, 0),
    )


def record_banner_events(
    db: Session,
    events: list[BannerEventIn],
    *,
    user_id: uuid.UUID | None = None,
) -> int:
    if not events:
        raise EmptyEventsError("events must not be empty")

    banner_ids = {event.banner_id for event in events}
    existing_ids = set(db.scalars(select(Banner.id).where(Banner.id.in_(banner_ids))).all())
    missing_ids = banner_ids - existing_ids
    if missing_ids:
        raise BannerNotFoundError("Banner not found")

    for event in events:
        db.add(
            BannerEvent(
                banner_id=event.banner_id,
                user_id=user_id,
                event=event.event,
                timestamp=event.timestamp or utcnow(),
            )
        )
    db.commit()
    return len(events)


def _active_banner_rows(db: Session) -> list[Banner]:
    now = utcnow()
    stmt = (
        select(Banner)
        .where(
            Banner.is_active.is_(True),
            or_(Banner.start_at.is_(None), Banner.start_at <= now),
            or_(Banner.end_at.is_(None), Banner.end_at >= now),
        )
        .order_by(Banner.priority.asc(), Banner.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def _active_collections_stmt():
    today = utcnow().date()
    return (
        select(Collection)
        .where(
            Collection.is_active.is_(True),
            or_(Collection.start_date.is_(None), Collection.start_date <= today),
        )
        .order_by(Collection.priority.asc(), Collection.created_at.asc())
    )


def _active_collections_subquery():
    return _active_collections_stmt().subquery()


def _collection_products(
    db: Session,
    b2b_client: B2BClient,
    collection: Collection,
    *,
    limit: int,
    offset: int,
) -> CollectionProductsResponse:
    all_rows = db.scalars(
        select(CollectionProduct)
        .where(CollectionProduct.collection_id == collection.id)
        .order_by(CollectionProduct.ordering.asc())
    ).all()
    page_rows = all_rows[offset : offset + limit]
    product_ids = [row.product_id for row in page_rows]
    products_by_id = _available_products_by_id(b2b_client.fetch_products_by_ids(product_ids))

    items: list[CatalogProductCard] = []
    unavailable_ids: list[uuid.UUID] = []
    for product_id in product_ids:
        product = products_by_id.get(str(product_id))
        if product is None:
            unavailable_ids.append(product_id)
            continue
        items.append(CatalogProductCard.model_validate(normalize_catalog_product_card(product)))

    return CollectionProductsResponse(
        collection_id=collection.id,
        collection_title=collection.title,
        items=items,
        unavailable_ids=unavailable_ids,
        total_products=len(all_rows),
        limit=limit,
        offset=offset,
    )


def _available_products_by_id(products: list[dict]) -> dict[str, dict]:
    result = {}
    for product in products:
        if is_hidden_catalog_product(product):
            continue
        product_id = product.get("id")
        if product_id is not None:
            result[str(product_id)] = product
    return result


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return min(max(value, minimum), maximum)
