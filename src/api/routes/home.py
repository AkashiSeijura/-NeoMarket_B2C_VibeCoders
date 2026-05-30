from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from src.api.deps import _user_id_from_authorization
from src.db.session import get_db
from src.schemas.home import (
    BannerEventsRequest,
    BannerEventsResponse,
    BannerResponse,
    CollectionProductsResponse,
    CollectionsResponse,
    OpenAPIBanner,
    OpenAPICollection,
)
from src.services.b2b_client import B2BClient, get_b2b_client
from src.services.home_service import (
    get_collection_products,
    list_active_banners,
    list_active_collections,
    list_active_openapi_banners,
    list_active_openapi_collections,
    record_banner_events,
)

router = APIRouter(tags=["Catalog"])


@router.get("/api/v1/catalog/banners", response_model=list[OpenAPIBanner], response_model_exclude_none=True)
def catalog_banners_endpoint(db: Session = Depends(get_db)) -> list[OpenAPIBanner]:
    return list_active_openapi_banners(db)


@router.get("/api/v1/home/banners", response_model=BannerResponse, include_in_schema=False)
def home_banners_endpoint(db: Session = Depends(get_db)) -> BannerResponse:
    return list_active_banners(db)


@router.get("/api/v1/main/collections", response_model=CollectionsResponse)
def main_collections_endpoint(
    limit: int = Query(default=10),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
) -> CollectionsResponse:
    return list_active_collections(db, limit=limit, offset=offset)


@router.get("/api/v1/catalog/collections", response_model=list[OpenAPICollection])
def catalog_collections_endpoint(
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> list[OpenAPICollection]:
    return list_active_openapi_collections(db, b2b_client)


@router.get("/api/v1/collections/{collection_id}/products", response_model=CollectionProductsResponse)
def collection_products_endpoint(
    collection_id: uuid.UUID,
    limit: int = Query(default=20),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CollectionProductsResponse:
    return get_collection_products(db, b2b_client, collection_id, limit=limit, offset=offset)


@router.post(
    "/api/v1/banner-events",
    response_model=BannerEventsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def banner_events_endpoint(
    payload: BannerEventsRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> BannerEventsResponse:
    user_id: uuid.UUID | None = _user_id_from_authorization(authorization) if authorization else None
    accepted_count = record_banner_events(db, payload.events, user_id=user_id)
    return BannerEventsResponse(accepted_count=accepted_count)
