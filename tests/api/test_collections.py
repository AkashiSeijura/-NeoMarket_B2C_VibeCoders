from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from src.models.home import Collection, CollectionProduct


def _collection(
    *,
    title: str = "Hits",
    priority: int = 1,
    is_active: bool = True,
    start_date=None,
) -> Collection:
    return Collection(
        title=title,
        description="Top products",
        cover_image_url="https://cdn.example.test/collection.jpg",
        target_url="https://example.test/catalog/hits",
        priority=priority,
        is_active=is_active,
        start_date=start_date,
    )


def _product(product_id: uuid.UUID, *, name: str = "Phone", status: str = "MODERATED") -> dict:
    return {
        "id": str(product_id),
        "name": name,
        "slug": name.lower(),
        "status": status,
        "min_price": 1000,
        "has_stock": True,
        "images": [{"id": "img-1", "url": "https://cdn.example.test/product.jpg", "ordering": 0}],
    }


def test_collections_list_returns_metadata_without_products(client, db_session):
    today = datetime.now(UTC).date()
    first = _collection(title="New", priority=1, start_date=today - timedelta(days=1))
    second = _collection(title="Hits", priority=2, start_date=today)
    inactive = _collection(title="Hidden", priority=0, is_active=False)
    future = _collection(title="Future", priority=0, start_date=today + timedelta(days=1))
    db_session.add_all([second, first, inactive, future])
    db_session.commit()

    response = client.get("/api/v1/main/collections?limit=10&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"] == {"total_count": 2, "limit": 10, "offset": 0}
    assert [item["id"] for item in payload["collections"]] == [str(first.id), str(second.id)]
    assert "products" not in payload["collections"][0]


def test_collection_products_enriched_from_b2b(client, db_session, fake_b2b):
    collection = _collection()
    first_product_id = uuid.uuid4()
    second_product_id = uuid.uuid4()
    db_session.add(collection)
    db_session.flush()
    db_session.add_all(
        [
            CollectionProduct(collection_id=collection.id, product_id=first_product_id, ordering=1),
            CollectionProduct(collection_id=collection.id, product_id=second_product_id, ordering=2),
        ]
    )
    db_session.commit()
    fake_b2b.catalog_products = [
        _product(second_product_id, name="Laptop"),
        _product(first_product_id, name="Phone"),
    ]

    response = client.get(f"/api/v1/collections/{collection.id}/products")

    assert response.status_code == 200
    payload = response.json()
    assert payload["collection_id"] == str(collection.id)
    assert payload["collection_title"] == "Hits"
    assert [item["id"] for item in payload["items"]] == [str(first_product_id), str(second_product_id)]
    assert [item["name"] for item in payload["items"]] == ["Phone", "Laptop"]
    assert payload["unavailable_ids"] == []


def test_unavailable_products_in_unavailable_ids(client, db_session, fake_b2b):
    collection = _collection()
    deleted_product_id = uuid.uuid4()
    missing_product_id = uuid.uuid4()
    db_session.add(collection)
    db_session.flush()
    db_session.add_all(
        [
            CollectionProduct(collection_id=collection.id, product_id=deleted_product_id, ordering=1),
            CollectionProduct(collection_id=collection.id, product_id=missing_product_id, ordering=2),
        ]
    )
    db_session.commit()
    deleted_product = _product(deleted_product_id, name="Blocked")
    deleted_product["deleted"] = True
    fake_b2b.catalog_products = [deleted_product]

    response = client.get(f"/api/v1/collections/{collection.id}/products")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["unavailable_ids"] == [str(deleted_product_id), str(missing_product_id)]


def test_unknown_collection_returns_404(client):
    response = client.get(f"/api/v1/collections/{uuid.uuid4()}/products")

    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "message": "Collection not found"}
