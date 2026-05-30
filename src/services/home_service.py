from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.models.base import utcnow
from src.models.home import Banner, BannerEvent
from src.schemas.home import BannerEventIn, BannerRead, BannerResponse, OpenAPIBanner
from src.services.errors import BannerNotFoundError, EmptyEventsError


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
