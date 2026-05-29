from __future__ import annotations

import uuid

from sqlalchemy import select

from src.models.cart import Favorite
from tests.conftest import auth_headers


def _product(product_id: uuid.UUID, *, title: str = "Phone", status: str = "MODERATED") -> dict:
    sku_id = uuid.uuid4()
    return {
        "id": str(product_id),
        "title": title,
        "status": status,
        "images": [{"id": "image-1", "url": "https://example.com/product.jpg", "ordering": 0}],
        "skus": [{"id": str(sku_id), "name": "Black", "price": 1000, "active_quantity": 5}],
    }


def test_add_to_favorites_returns_201(client, fake_b2b):
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    fake_b2b.catalog_products.append(_product(product_id))

    response = client.post(f"/api/v1/favorites/{product_id}", headers=auth_headers(user_id))

    assert response.status_code == 201
    assert response.json()["product_id"] == str(product_id)


def test_get_favorites_enriched_from_b2b(client, fake_b2b):
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    fake_b2b.catalog_products.append(_product(product_id, title="Laptop"))
    client.post(f"/api/v1/favorites/{product_id}", headers=auth_headers(user_id))

    response = client.get("/api/v1/favorites", headers=auth_headers(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["id"] == str(product_id)
    assert body["items"][0]["name"] == "Laptop"


def test_repeat_add_returns_200_not_duplicate(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    fake_b2b.catalog_products.append(_product(product_id))

    first = client.post(f"/api/v1/favorites/{product_id}", headers=auth_headers(user_id))
    second = client.post(f"/api/v1/favorites/{product_id}", headers=auth_headers(user_id))

    rows = db_session.scalars(select(Favorite).where(Favorite.user_id == user_id)).all()
    assert first.status_code == 201
    assert second.status_code == 200
    assert len(rows) == 1


def test_blocked_product_excluded_from_list(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    visible_id = uuid.uuid4()
    blocked_id = uuid.uuid4()
    fake_b2b.catalog_products.append(_product(visible_id, title="Visible"))
    fake_b2b.catalog_products.append(_product(blocked_id, title="Blocked", status="BLOCKED"))
    db_session.add_all(
        [
            Favorite(user_id=user_id, product_id=visible_id),
            Favorite(user_id=user_id, product_id=blocked_id),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/favorites", headers=auth_headers(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert [item["id"] for item in body["items"]] == [str(visible_id)]


def test_user_id_from_query_is_ignored(client, fake_b2b):
    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()
    owner_product_id = uuid.uuid4()
    attacker_product_id = uuid.uuid4()
    fake_b2b.catalog_products.extend(
        [
            _product(owner_product_id, title="Owner"),
            _product(attacker_product_id, title="Attacker"),
        ]
    )
    client.post(f"/api/v1/favorites/{owner_product_id}", headers=auth_headers(owner_id))
    client.post(f"/api/v1/favorites/{attacker_product_id}", headers=auth_headers(attacker_id))

    response = client.get(
        f"/api/v1/favorites?user_id={owner_id}",
        headers=auth_headers(attacker_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["id"] == str(attacker_product_id)
