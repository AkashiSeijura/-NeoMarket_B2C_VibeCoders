from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from src.models.home import Banner, BannerEvent


def _banner(
    *,
    title: str,
    priority: int,
    is_active: bool = True,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> Banner:
    return Banner(
        title=title,
        image_url="https://cdn.example.test/banner.jpg",
        link="https://example.test/catalog",
        priority=priority,
        is_active=is_active,
        start_at=start_at,
        end_at=end_at,
    )


def test_active_banners_returned_sorted_by_priority(client, db_session):
    now = datetime.now(UTC)
    higher = _banner(
        title="Higher",
        priority=10,
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=1),
    )
    lower = _banner(
        title="Lower",
        priority=1,
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=1),
    )
    inactive = _banner(title="Inactive", priority=0, is_active=False)
    future = _banner(title="Future", priority=0, start_at=now + timedelta(days=1))
    expired = _banner(title="Expired", priority=0, end_at=now - timedelta(seconds=1))
    db_session.add_all([higher, lower, inactive, future, expired])
    db_session.commit()

    response = client.get("/api/v1/home/banners")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 2
    assert [item["id"] for item in payload["items"]] == [str(lower.id), str(higher.id)]
    assert [item["priority"] for item in payload["items"]] == [1, 10]


def test_no_active_banners_returns_200_empty(client, db_session):
    db_session.add(_banner(title="Inactive", priority=1, is_active=False))
    db_session.commit()

    response = client.get("/api/v1/home/banners")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total_count": 0}


def test_click_on_unknown_banner_returns_400(client):
    response = client.post(
        "/api/v1/banner-events",
        json={"events": [{"banner_id": str(uuid.uuid4()), "event": "click"}]},
    )

    assert response.status_code == 400
    assert response.json() == {"code": "BANNER_NOT_FOUND", "message": "Banner not found"}


def test_banner_events_are_recorded(client, db_session):
    banner = _banner(title="Sale", priority=1)
    db_session.add(banner)
    db_session.commit()

    response = client.post(
        "/api/v1/banner-events",
        json={
            "events": [
                {"banner_id": str(banner.id), "event": "impression"},
                {"banner_id": str(banner.id), "event": "click"},
            ]
        },
    )

    assert response.status_code == 202
    assert response.json() == {"accepted_count": 2}
    assert db_session.query(BannerEvent).count() == 2


def test_catalog_banners_openapi_shape(client, db_session):
    banner = _banner(title="Sale", priority=3)
    db_session.add(banner)
    db_session.commit()

    response = client.get("/api/v1/catalog/banners")

    assert response.status_code == 200
    assert response.json()[0]["ordering"] == 3
