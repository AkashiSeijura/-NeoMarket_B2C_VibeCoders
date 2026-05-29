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


def test_search_returns_matching_products(client, fake_b2b):
    category_id = uuid.uuid4()
    another_category_id = uuid.uuid4()
    fake_b2b.catalog_products = [
        _product(category_id=category_id, name="iPhone 15 Pro", min_price=120000, brand="Apple"),
        {
            **_product(category_id=category_id, name="Coffee Grinder", min_price=15000, brand="Neo"),
            "description": "Fresh espresso accessory",
        },
        _product(category_id=category_id, name="Android Phone", min_price=90000, brand="Samsung"),
        _product(category_id=another_category_id, name="iPhone Case", min_price=1000, brand="Apple"),
    ]

    title_response = client.get(
        "/api/v1/products",
        params={"search": "iphone", "category_id": str(category_id), "filters[brand]": "Apple"},
    )
    description_response = client.get("/api/v1/products", params={"search": "espresso"})

    assert title_response.status_code == 200
    title_payload = title_response.json()
    assert title_payload["total_count"] == 1
    assert [item["name"] for item in title_payload["items"]] == ["iPhone 15 Pro"]
    assert ("search", "iphone") in fake_b2b.catalog_calls[-2]
    assert ("filter[category_id]", str(category_id)) in fake_b2b.catalog_calls[-2]
    assert ("filter[attributes][brand]", "Apple") in fake_b2b.catalog_calls[-2]

    assert description_response.status_code == 200
    description_payload = description_response.json()
    assert description_payload["total_count"] == 1
    assert description_payload["items"][0]["name"] == "Coffee Grinder"


def test_short_query_returns_400(client):
    response = client.get("/api/v1/products", params={"search": "ab"})

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "Search query must be at least 3 characters",
    }


def test_special_chars_do_not_break_query(client, fake_b2b):
    fake_b2b.catalog_products = [
        _product(category_id=uuid.uuid4(), name="iPhone%15", min_price=120000, brand="Apple"),
        _product(category_id=uuid.uuid4(), name="Coffee Maker", min_price=15000, brand="Neo"),
    ]

    percent_response = client.get("/api/v1/products", params={"search": "iPhone%15"})
    quote_response = client.get("/api/v1/products", params={"search": "кофе'"})
    underscore_response = client.get("/api/v1/products", params={"search": "foo_bar"})

    assert percent_response.status_code == 200
    assert [item["name"] for item in percent_response.json()["items"]] == ["iPhone%15"]
    assert quote_response.status_code == 200
    assert quote_response.json()["items"] == []
    assert underscore_response.status_code == 200
    assert underscore_response.json()["items"] == []


def test_empty_results_returns_200(client, fake_b2b):
    fake_b2b.catalog_products = [
        _product(category_id=uuid.uuid4(), name="Phone", min_price=120000, brand="Apple"),
    ]

    response = client.get("/api/v1/products", params={"search": "does-not-exist"})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total_count"] == 0


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


def test_category_tree_returns_nested_structure(client, fake_b2b):
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    leaf_id = uuid.uuid4()
    fake_b2b.categories = [
        {"id": str(child_id), "name": "Smartphones", "slug": "smartphones", "parent_id": str(root_id)},
        {"id": str(root_id), "name": "Electronics", "slug": "electronics", "parent_id": None},
        {"id": str(leaf_id), "name": "Android", "slug": "android", "parent_id": str(child_id)},
    ]

    response = client.get("/api/v1/catalog/categories/tree")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == str(root_id)
    assert payload[0]["level"] == 0
    assert payload[0]["children"][0]["id"] == str(child_id)
    assert payload[0]["children"][0]["children"][0]["id"] == str(leaf_id)


def test_category_tree_flow_alias_wraps_items(client, fake_b2b):
    category_id = uuid.uuid4()
    fake_b2b.categories = [{"id": str(category_id), "name": "Clothes", "parent_id": None}]

    response = client.get("/api/v1/categories")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(category_id)


def test_category_detail_returns_category_metadata(client, fake_b2b):
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    fake_b2b.categories = [
        {"id": str(root_id), "name": "Electronics", "slug": "electronics", "parent_id": None},
        {
            "id": str(child_id),
            "name": "Smartphones",
            "slug": "smartphones",
            "description": "Mobile phones",
            "parent_id": str(root_id),
        },
    ]
    fake_b2b.catalog_products = [
        _product(category_id=child_id, name="Phone", min_price=120000, brand="Neo"),
    ]

    response = client.get(f"/api/v1/catalog/categories/{child_id}?include_product_count=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(child_id)
    assert payload["parent"]["id"] == str(root_id)
    assert payload["product_count"] == 1


def test_breadcrumbs_return_path_from_root(client, fake_b2b):
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    leaf_id = uuid.uuid4()
    fake_b2b.categories = [
        {"id": str(root_id), "name": "Electronics", "slug": "electronics", "parent_id": None},
        {"id": str(child_id), "name": "Smartphones", "slug": "smartphones", "parent_id": str(root_id)},
        {"id": str(leaf_id), "name": "Android", "slug": "android", "parent_id": str(child_id)},
    ]

    response = client.get(f"/api/v1/breadcrumbs?category_id={leaf_id}")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["data"]] == [str(root_id), str(child_id), str(leaf_id)]
    assert [item["url"] for item in payload["data"]] == [
        "/catalog/electronics",
        "/catalog/electronics/smartphones",
        "/catalog/electronics/smartphones/android",
    ]
    assert payload["data"][-1]["is_current"] is True
    assert payload["meta"]["resolved_via"] == "category_id"


def test_breadcrumbs_resolve_product_category(client, fake_b2b):
    category_id = uuid.uuid4()
    product_id = uuid.uuid4()
    fake_b2b.categories = [{"id": str(category_id), "name": "Electronics", "slug": "electronics", "parent_id": None}]
    fake_b2b.catalog_product = {
        "id": str(product_id),
        "name": "Phone",
        "status": "MODERATED",
        "deleted": False,
        "category_id": str(category_id),
    }

    response = client.get(f"/api/v1/breadcrumbs?product_id={product_id}")

    assert response.status_code == 200
    assert response.json()["meta"]["resolved_via"] == "product_id"
    assert response.json()["data"][0]["id"] == str(category_id)


def test_unknown_category_returns_404(client, fake_b2b):
    response = client.get(f"/api/v1/breadcrumbs?category_id={uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_ambiguous_params_returns_400(client):
    response = client.get(f"/api/v1/breadcrumbs?category_id={uuid.uuid4()}&product_id={uuid.uuid4()}")

    assert response.status_code == 400
    assert response.json() == {
        "error": "ambiguous_param",
        "message": "only one of category_id or product_id must be provided",
    }


def test_missing_breadcrumb_param_returns_400(client):
    response = client.get("/api/v1/breadcrumbs")

    assert response.status_code == 400
    assert response.json() == {
        "error": "missing_param",
        "message": "category_id or product_id must be provided",
    }


def test_orphan_node_returns_422(client, fake_b2b):
    category_id = uuid.uuid4()
    fake_b2b.categories = [
        {"id": str(category_id), "name": "Orphan", "parent_id": str(uuid.uuid4())},
    ]

    response = client.get(f"/api/v1/breadcrumbs?category_id={category_id}")

    assert response.status_code == 422
    assert response.json() == {
        "error": "orphan_node",
        "message": "category hierarchy is broken",
    }


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


def _product_detail_payload(product_id: uuid.UUID | None = None) -> dict:
    return {
        "id": str(product_id or uuid.uuid4()),
        "slug": "phone-pro",
        "title": "Phone Pro",
        "description": "Flagship phone",
        "status": "MODERATED",
        "deleted": False,
        "category_id": str(uuid.uuid4()),
        "images": [{"id": str(uuid.uuid4()), "url": "https://cdn.example.test/front.jpg", "ordering": 0}],
        "characteristics": [{"name": "Brand", "value": "Neo"}],
        "skus": [
            {
                "id": str(uuid.uuid4()),
                "name": "128 GB Black",
                "article": "BLK-128",
                "price": 120000,
                "discount": 0,
                "active_quantity": 3,
                "cost_price": 80000,
                "reserved_quantity": 1,
                "characteristics": [{"name": "Color", "value": "Black"}],
                "image": "https://cdn.example.test/black.jpg",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "256 GB White",
                "article": "WHT-256",
                "price": 150000,
                "discount": 10000,
                "active_quantity": 0,
                "cost_price": 90000,
                "reserved_quantity": 0,
            },
        ],
    }


def test_product_card_returns_full_data_with_skus(client, fake_b2b):
    product_id = uuid.uuid4()
    fake_b2b.catalog_product = _product_detail_payload(product_id)

    response = client.get(f"/api/v1/catalog/products/{product_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(product_id)
    assert payload["name"] == "Phone Pro"
    assert payload["description"] == "Flagship phone"
    assert payload["images"]
    assert payload["attributes"]["Brand"] == "Neo"
    assert payload["min_price"] == 120000
    assert payload["has_stock"] is True
    assert len(payload["skus"]) == 2
    assert payload["skus"][0]["price"] == 120000
    assert payload["skus"][0]["available_quantity"] == 3
    assert payload["skus"][1]["price"] == 140000
    assert payload["skus"][1]["old_price"] == 150000
    assert payload["skus"][1]["available_quantity"] == 0


def test_cost_price_absent_in_response(client, fake_b2b):
    product_id = uuid.uuid4()
    fake_b2b.catalog_product = _product_detail_payload(product_id)

    response = client.get(f"/api/v1/catalog/products/{product_id}")

    assert response.status_code == 200
    for sku in response.json()["skus"]:
        assert "cost_price" not in sku
        assert "reserved_quantity" not in sku


def test_blocked_product_returns_404(client, fake_b2b):
    product_id = uuid.uuid4()
    payload = _product_detail_payload(product_id)
    payload["status"] = "BLOCKED"
    fake_b2b.catalog_product = payload

    response = client.get(f"/api/v1/catalog/products/{product_id}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_sku_without_stock_is_shown_as_unavailable(client, fake_b2b):
    product_id = uuid.uuid4()
    fake_b2b.catalog_product = _product_detail_payload(product_id)

    response = client.get(f"/api/v1/products/{product_id}")

    assert response.status_code == 200
    out_of_stock_sku = response.json()["skus"][1]
    assert out_of_stock_sku["available_quantity"] == 0


def test_similar_returns_up_to_8_from_same_category(client, fake_b2b):
    category_id = uuid.uuid4()
    product_id = uuid.uuid4()
    current = _product(
        product_id=product_id,
        category_id=category_id,
        name="Phone Current",
        min_price=100000,
        brand="Neo",
    )
    current["status"] = "MODERATED"
    similar = [
        _product(
            category_id=category_id,
            name=f"Phone Similar {index}",
            min_price=90000 + index,
            brand="Neo",
            popularity=index,
        )
        for index in range(10)
    ]
    fake_b2b.catalog_products = [current, *similar]

    response = client.get(f"/api/v1/products/{product_id}/similar")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 8
    assert str(product_id) not in {item["id"] for item in payload}
    assert {item["category"]["id"] for item in payload} == {str(category_id)}


def test_empty_category_returns_200_empty_list(client, fake_b2b):
    category_id = uuid.uuid4()
    product_id = uuid.uuid4()
    current = _product(
        product_id=product_id,
        category_id=category_id,
        name="Only Phone",
        min_price=100000,
        brand="Neo",
    )
    current["status"] = "MODERATED"
    fake_b2b.catalog_products = [current]

    response = client.get(f"/api/v1/products/{product_id}/similar")

    assert response.status_code == 200
    assert response.json() == []


def test_unknown_product_returns_404(client):
    response = client.get(f"/api/v1/products/{uuid.uuid4()}/similar")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_similar_fallback_uses_parent_category(client, fake_b2b):
    child_category_id = uuid.uuid4()
    parent_category_id = uuid.uuid4()
    product_id = uuid.uuid4()
    current = _product(
        product_id=product_id,
        category_id=child_category_id,
        name="Only Child Phone",
        min_price=100000,
        brand="Neo",
    )
    current["status"] = "MODERATED"
    current["category"] = {"id": str(child_category_id), "parent_id": str(parent_category_id)}
    parent_product = _product(
        category_id=parent_category_id,
        name="Parent Category Phone",
        min_price=90000,
        brand="Neo",
    )
    fake_b2b.catalog_products = [current, parent_product]

    response = client.get(f"/api/v1/catalog/products/{product_id}/similar")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [parent_product["id"]]
