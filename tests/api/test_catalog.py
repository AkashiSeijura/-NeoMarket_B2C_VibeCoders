from __future__ import annotations

import uuid

import httpx

import src.services.b2b_client as b2b_module
from src.services.b2b_client import B2BClient


def _product(
    *,
    product_id: uuid.UUID | None = None,
    category_id: uuid.UUID,
    name: str,
    min_price: int,
    brand: str,
    popularity: int = 0,
) -> dict:
    return {
        "id": str(product_id or uuid.uuid4()),
        "category_id": str(category_id),
        "name": name,
        "min_price": min_price,
        "has_stock": True,
        "popularity": popularity,
        "attributes": {"brand": brand},
        "images": [{"id": str(uuid.uuid4()), "url": "https://cdn.example.test/product.jpg", "ordering": 0}],
    }


def test_catalog_returns_filtered_sorted_products(client, fake_b2b):
    category_id = uuid.uuid4()
    another_category_id = uuid.uuid4()
    fake_b2b.catalog_products = [
        _product(category_id=category_id, name="Phone Pro", min_price=120000, brand="Apple", popularity=3),
        _product(category_id=category_id, name="Phone Mini", min_price=90000, brand="Apple", popularity=2),
        _product(category_id=category_id, name="Phone Ultra", min_price=150000, brand="Samsung", popularity=9),
        _product(category_id=another_category_id, name="Phone Case", min_price=1000, brand="Apple", popularity=1),
    ]

    response = client.get(
        "/api/v1/catalog/products",
        params={
            "category_id": str(category_id),
            "filters[brand]": "Apple",
            "sort": "price_asc",
            "limit": "1",
            "offset": "0",
            "q": "phone",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 2
    assert payload["limit"] == 1
    assert [item["min_price"] for item in payload["items"]] == [90000]
    assert payload["items"][0]["name"] == "Phone Mini"
    assert {"id", "name", "min_price", "has_stock", "images"} <= set(payload["items"][0])
    assert {"id", "url", "ordering"} <= set(payload["items"][0]["images"][0])

    forwarded = fake_b2b.catalog_calls[-1]
    assert ("q", "phone") in forwarded
    assert ("filter[category_id]", str(category_id)) in forwarded
    assert ("filter[attributes][brand]", "Apple") in forwarded


def test_products_flow_alias_is_supported(client, fake_b2b):
    category_id = uuid.uuid4()
    fake_b2b.catalog_products = [
        {
            "id": str(uuid.uuid4()),
            "category_id": str(category_id),
            "title": "Flow Shape Phone",
            "price": 70000,
            "in_stock": True,
            "image": "https://cdn.example.test/flow.jpg",
        }
    ]

    response = client.get(f"/api/v1/products?category_id={category_id}&sort=price_asc")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["name"] == "Flow Shape Phone"
    assert item["min_price"] == 70000
    assert item["has_stock"] is True


def test_facets_return_counts_per_filter_value(client, fake_b2b):
    category_id = uuid.uuid4()
    fake_b2b.catalog_products = [
        _product(category_id=category_id, name="Phone Pro", min_price=120000, brand="Apple"),
        _product(category_id=category_id, name="Phone Mini", min_price=90000, brand="Apple"),
        _product(category_id=category_id, name="Phone Ultra", min_price=150000, brand="Samsung"),
    ]

    response = client.get(f"/api/v1/catalog/facets?category_id={category_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["category_id"] == str(category_id)
    brand_facet = next(item for item in payload["facets"] if item["name"] == "brand")
    assert {"value": "Apple", "count": 2} in brand_facet["values"]
    assert {"value": "Samsung", "count": 1} in brand_facet["values"]


def test_invalid_sort_returns_400(client):
    response = client.get("/api/v1/catalog/products?sort=rating")

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "INVALID_SORT"
    assert "price_asc" in payload["message"]
    assert "new" in payload["message"]


def test_b2b_unavailable_returns_502(client, fake_b2b):
    fake_b2b.fail_catalog = True

    response = client.get("/api/v1/catalog/products?limit=10")

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"


def test_catalog_b2b_client_uses_service_key(monkeypatch):
    captured = {}

    class FakeHttpClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, params, headers):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return httpx.Response(200, json={"items": [], "total_count": 0, "limit": 20, "offset": 0})

    monkeypatch.setattr(b2b_module.httpx, "Client", FakeHttpClient)

    payload = B2BClient(base_url="http://b2b:8000", service_key="secret-key").fetch_catalog_products([("q", "phone")])

    assert payload["items"] == []
    assert captured["url"] == "http://b2b:8000/api/v1/products"
    assert captured["params"] == [("q", "phone")]
    assert captured["headers"]["X-Service-Key"] == "secret-key"
