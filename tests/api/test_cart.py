from __future__ import annotations

import uuid

from tests.conftest import auth_headers


def test_add_sku_increments_quantity_if_already_in_cart(client, fake_b2b):
    sku_id = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=10)
    headers = {"X-Session-Id": str(uuid.uuid4())}

    first = client.post("/api/v1/cart/items", json={"sku_id": str(sku_id), "quantity": 1}, headers=headers)
    second = client.post("/api/v1/cart/items", json={"sku_id": str(sku_id), "quantity": 2}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["items"][0]["quantity"] == 3
    assert second.json()["items_count"] == 3


def test_get_cart_enriched_with_b2b_data(client, fake_b2b):
    sku_id = uuid.uuid4()
    product_id = uuid.uuid4()
    fake_b2b.set_sku(
        sku_id,
        product_id=product_id,
        product_title="iPhone 15",
        sku_name="256GB Black",
        unit_price=12999000,
        active_quantity=5,
    )
    headers = {"X-Session-Id": str(uuid.uuid4())}

    client.post("/api/v1/cart/items", json={"sku_id": str(sku_id), "quantity": 2}, headers=headers)
    response = client.get("/api/v1/cart", headers=headers)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["product_id"] == str(product_id)
    assert item["name"] == "iPhone 15 256GB Black"
    assert item["product_title"] == "iPhone 15"
    assert item["sku_name"] == "256GB Black"
    assert item["unit_price"] == 12999000
    assert item["line_total"] == 25998000
    assert item["available_quantity"] == 5
    assert item["is_available"] is True
    assert response.json()["subtotal"] == 25998000
    assert response.json()["summary"]["total_amount"] == 25998000


def test_unavailable_sku_shown_with_reason(client, fake_b2b):
    sku_id = uuid.uuid4()
    fake_b2b.set_sku(sku_id, unit_price=5000, active_quantity=3)
    headers = {"X-Session-Id": str(uuid.uuid4())}
    client.post("/api/v1/cart/items", json={"sku_id": str(sku_id), "quantity": 1}, headers=headers)

    fake_b2b.set_sku(sku_id, unit_price=5000, active_quantity=0)
    response = client.get("/api/v1/cart", headers=headers)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["is_available"] is False
    assert item["unavailable_reason"] == "OUT_OF_STOCK"
    assert item["line_total"] == 0
    assert response.json()["subtotal"] == 0
    assert response.json()["is_valid"] is False
    assert response.json()["summary"]["total_amount"] == 0
    assert response.json()["summary"]["checkout_ready"] is False


def test_guest_cart_merged_on_login(client, fake_b2b):
    sku_id = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=10)
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()

    client.post(
        "/api/v1/cart/items",
        json={"sku_id": str(sku_id), "quantity": 2},
        headers={"X-Session-Id": str(session_id)},
    )
    client.post(
        "/api/v1/cart/items",
        json={"sku_id": str(sku_id), "quantity": 5},
        headers=auth_headers(user_id),
    )

    merged = client.post(
        "/api/v1/cart/merge",
        headers={**auth_headers(user_id), "X-Session-Id": str(session_id)},
    )
    guest_cart = client.get("/api/v1/cart", headers={"X-Session-Id": str(session_id)})

    assert merged.status_code == 200
    assert merged.json()["items"][0]["quantity"] == 5
    assert guest_cart.json()["items"] == []


def test_cart_openapi_patch_delete_and_validate_by_sku(client, fake_b2b):
    sku_id = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=2)
    headers = {"X-Session-Id": str(uuid.uuid4())}

    client.post("/api/v1/cart/items", json={"sku_id": str(sku_id), "quantity": 1}, headers=headers)
    patched = client.patch(f"/api/v1/cart/items/{sku_id}", json={"quantity": 2}, headers=headers)
    validation = client.post("/api/v1/cart/validate", headers=headers)
    deleted = client.delete(f"/api/v1/cart/items/{sku_id}", headers=headers)

    assert patched.status_code == 200
    assert patched.json()["items"][0]["quantity"] == 2
    assert validation.status_code == 200
    assert validation.json()["is_valid"] is True
    assert validation.json()["issues"] == []
    assert deleted.status_code == 200
    assert deleted.json()["items"] == []
