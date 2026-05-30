from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from src.api.deps import _user_id_from_authorization
from src.db.session import get_db
from src.schemas.home import BannerEventsRequest, BannerEventsResponse, BannerResponse, OpenAPIBanner
from src.services.home_service import list_active_banners, list_active_openapi_banners, record_banner_events

router = APIRouter(tags=["Catalog"])


@router.get("/api/v1/catalog/banners", response_model=list[OpenAPIBanner], response_model_exclude_none=True)
def catalog_banners_endpoint(db: Session = Depends(get_db)) -> list[OpenAPIBanner]:
    return list_active_openapi_banners(db)


@router.get("/api/v1/home/banners", response_model=BannerResponse, include_in_schema=False)
def home_banners_endpoint(db: Session = Depends(get_db)) -> BannerResponse:
    return list_active_banners(db)


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
