from __future__ import annotations

import uuid

from sqlalchemy import select

from src.models.cart import CartItem
from src.models.order import Order, OrderItem
from tests.conftest import auth_headers


SERVICE_HEADERS = {"X-Service-Key": "dev-b2b-to-b2c-key"}


def _event_payload(idempotency_key: uuid.UUID, product_id: uuid.UUID, sku_ids: list[uuid.UUID]) -> dict:
    return {
        "idempotency_key": str(idempotency_key),
        "event": "PRODUCT_BLOCKED",
        "product_id": str(product_id),
        "sku_ids": [str(sku_id) for sku_id in sku_ids],
        "reason": "Moderation blocked product",
        "date": "2026-04-16T12:00:00Z",
    }


def _order_payload(idempotency_key: uuid.UUID, sku_id: uuid.UUID) -> dict:
    return {
        "idempotency_key": str(idempotency_key),
        "items": [{"sku_id": str(sku_id), "quantity": 1}],
        "delivery_address": "Yekaterinburg, Mira 19",
    }


def test_product_blocked_marks_cart_items_unavailable(client, fake_b2b, db_session):
    product_id = uuid.uuid4()
    sku_1 = uuid.uuid4()
    sku_2 = uuid.uuid4()
    untouched_sku = uuid.uuid4()
    fake_b2b.set_sku(sku_1, product_id=product_id, active_quantity=5)
    fake_b2b.set_sku(sku_2, product_id=product_id, active_quantity=5)
    fake_b2b.set_sku(untouched_sku, active_quantity=5)
    headers = {"X-Session-Id": str(uuid.uuid4())}
    client.post("/api/v1/cart/items", json={"sku_id": str(sku_1), "quantity": 1}, headers=headers)
    client.post("/api/v1/cart/items", json={"sku_id": str(sku_2), "quantity": 1}, headers=headers)
    client.post("/api/v1/cart/items", json={"sku_id": str(untouched_sku), "quantity": 1}, headers=headers)

    response = client.post(
        "/api/v1/events/product",
        json=_event_payload(uuid.uuid4(), product_id, [sku_1, sku_2]),
        headers=SERVICE_HEADERS,
    )
    cart = client.get("/api/v1/cart", headers=headers).json()
    items = {item["sku_id"]: item for item in cart["items"]}

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert items[str(sku_1)]["unavailable_reason"] == "PRODUCT_BLOCKED"
    assert items[str(sku_2)]["unavailable_reason"] == "PRODUCT_BLOCKED"
    assert items[str(untouched_sku)]["unavailable_reason"] is None
    assert cart["is_valid"] is False


def test_orders_not_affected_by_product_blocked(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    fake_b2b.set_sku(
        sku_id,
        product_id=product_id,
        product_title="Phone",
        sku_name="Black",
        unit_price=5000,
        active_quantity=5,
    )
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(uuid.uuid4(), sku_id),
        headers=auth_headers(user_id),
    )
    order_id = uuid.UUID(created.json()["id"])
    before = db_session.get(Order, order_id)
    before_item = before.items[0]
    before_snapshot = (before.status, before.total, before_item.unit_price, before_item.product_title)

    response = client.post(
        "/api/v1/events/product",
        json=_event_payload(uuid.uuid4(), product_id, [sku_id]),
        headers=SERVICE_HEADERS,
    )
    db_session.expire_all()
    after = db_session.get(Order, order_id)
    after_item = after.items[0]

    assert response.status_code == 200
    assert (after.status, after.total, after_item.unit_price, after_item.product_title) == before_snapshot
    assert db_session.scalars(select(OrderItem).where(OrderItem.sku_id == sku_id)).one().order_id == order_id


def test_idempotent_event_no_side_effects(client, fake_b2b, db_session):
    product_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, product_id=product_id, active_quantity=5)
    first_headers = {"X-Session-Id": str(uuid.uuid4())}
    client.post("/api/v1/cart/items", json={"sku_id": str(sku_id), "quantity": 1}, headers=first_headers)

    payload = _event_payload(idempotency_key, product_id, [sku_id])
    first = client.post("/api/v1/events/product", json=payload, headers=SERVICE_HEADERS)
    db_session.add(
        CartItem(
            session_id=str(uuid.uuid4()),
            sku_id=sku_id,
            product_id=product_id,
            quantity=1,
        )
    )
    db_session.commit()
    second = client.post("/api/v1/events/product", json=payload, headers=SERVICE_HEADERS)
    reasons = db_session.scalars(
        select(CartItem.unavailable_reason).where(CartItem.sku_id == sku_id).order_by(CartItem.created_at)
    ).all()

    assert first.status_code == 200
    assert second.status_code == 200
    assert reasons == ["PRODUCT_BLOCKED", None]


def test_missing_service_key_returns_401(client):
    product_id = uuid.uuid4()
    sku_id = uuid.uuid4()

    response = client.post(
        "/api/v1/events/product",
        json=_event_payload(uuid.uuid4(), product_id, [sku_id]),
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_openapi_b2b_events_endpoint_accepts_product_event(client, fake_b2b):
    product_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    fake_b2b.set_sku(sku_id, product_id=product_id, active_quantity=5)
    headers = {"X-Session-Id": str(uuid.uuid4())}
    client.post("/api/v1/cart/items", json={"sku_id": str(sku_id), "quantity": 1}, headers=headers)

    response = client.post(
        "/api/v1/b2b/events",
        json={
            "event_type": "PRODUCT_BLOCKED",
            "idempotency_key": str(uuid.uuid4()),
            "occurred_at": "2026-04-16T12:00:00Z",
            "payload": {"product_id": str(product_id), "reason": "Moderation blocked product"},
        },
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 200
    assert client.get("/api/v1/cart", headers=headers).json()["items"][0]["unavailable_reason"] == "PRODUCT_BLOCKED"
