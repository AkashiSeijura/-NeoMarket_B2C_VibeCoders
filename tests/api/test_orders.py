from __future__ import annotations

import logging
import uuid

from src.models.order import Order
from src.services.order_service import retry_delivered_fulfillments, transition_order_status
from tests.conftest import auth_headers


def _order_payload(idempotency_key: uuid.UUID, sku_id: uuid.UUID, quantity: int = 2) -> dict:
    return {
        "idempotency_key": str(idempotency_key),
        "items": [{"sku_id": str(sku_id), "quantity": quantity}],
        "delivery_address": "Yekaterinburg, Mira 19",
    }


def test_checkout_creates_paid_order_with_fixed_prices(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    product_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(
        sku_id,
        product_id=product_id,
        product_title="iPhone 15",
        sku_name="256GB Black",
        unit_price=12999000,
        active_quantity=5,
    )

    response = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id),
        headers={**auth_headers(user_id), "Idempotency-Key": str(idempotency_key)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PAID"
    assert body["buyer_id"] == str(user_id)
    assert body["total_amount"] == 25998000
    item = body["items"][0]
    assert item["sku_id"] == str(sku_id)
    assert item["product_id"] == str(product_id)
    assert item["product_title"] == "iPhone 15"
    assert item["sku_name"] == "256GB Black"
    assert item["unit_price"] == 12999000
    assert item["line_total"] == 25998000
    order = db_session.get(Order, uuid.UUID(body["id"]))
    assert order.items[0].unit_price == 12999000
    assert order.items[0].product_title == "iPhone 15"
    assert order.items[0].sku_name == "256GB Black"


def test_partial_reserve_failure_returns_409(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    sku_ok = uuid.uuid4()
    sku_failed = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_ok, active_quantity=5)
    fake_b2b.set_sku(sku_failed, active_quantity=5)
    fake_b2b.reserve_failed_items = [{"sku_id": str(sku_failed), "reason": "INSUFFICIENT_STOCK"}]

    response = client.post(
        "/api/v1/orders",
        json={
            "idempotency_key": str(idempotency_key),
            "items": [
                {"sku_id": str(sku_ok), "quantity": 1},
                {"sku_id": str(sku_failed), "quantity": 1},
            ],
        },
        headers=auth_headers(user_id),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "RESERVE_FAILED"
    assert response.json()["failed_items"] == fake_b2b.reserve_failed_items
    assert db_session.query(Order).count() == 0


def test_idempotency_returns_existing_order(client, fake_b2b):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, unit_price=5000, active_quantity=5)
    payload = _order_payload(idempotency_key, sku_id, quantity=1)
    headers = {**auth_headers(user_id), "Idempotency-Key": str(idempotency_key)}

    first = client.post("/api/v1/orders", json=payload, headers=headers)
    fake_b2b.set_sku(sku_id, unit_price=9999, active_quantity=5)
    second = client.post("/api/v1/orders", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["items"][0]["unit_price"] == 5000
    assert len(fake_b2b.reserve_calls) == 1


def test_b2b_unavailable_returns_503(client, fake_b2b):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    fake_b2b.fail_reserve_unavailable = True

    response = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(user_id),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "B2B_UNAVAILABLE"


def test_orders_list_returns_own_orders_paginated(client, fake_b2b, db_session):
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    paid_sku_1 = uuid.uuid4()
    paid_sku_2 = uuid.uuid4()
    delivered_sku = uuid.uuid4()
    other_sku = uuid.uuid4()
    for sku_id in [paid_sku_1, paid_sku_2, delivered_sku, other_sku]:
        fake_b2b.set_sku(sku_id, active_quantity=5)

    paid_1 = client.post(
        "/api/v1/orders",
        json=_order_payload(uuid.uuid4(), paid_sku_1, quantity=1),
        headers=auth_headers(owner_id),
    )
    paid_2 = client.post(
        "/api/v1/orders",
        json=_order_payload(uuid.uuid4(), paid_sku_2, quantity=1),
        headers=auth_headers(owner_id),
    )
    delivered = client.post(
        "/api/v1/orders",
        json=_order_payload(uuid.uuid4(), delivered_sku, quantity=1),
        headers=auth_headers(owner_id),
    )
    other = client.post(
        "/api/v1/orders",
        json=_order_payload(uuid.uuid4(), other_sku, quantity=1),
        headers=auth_headers(other_id),
    )
    delivered_order = db_session.get(Order, uuid.UUID(delivered.json()["id"]))
    delivered_order.status = "DELIVERED"
    db_session.commit()

    response = client.get(
        "/api/v1/orders?status=PAID&limit=1&offset=1",
        headers=auth_headers(owner_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] in {paid_1.json()["id"], paid_2.json()["id"]}
    assert body["items"][0]["id"] != other.json()["id"]
    assert body["items"][0]["status"] == "PAID"
    assert body["items"][0]["items"][0]["unit_price"] == 1000


def test_order_detail_shows_fixed_prices(client, fake_b2b):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, unit_price=5000, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=2),
        headers=auth_headers(user_id),
    )
    fake_b2b.set_sku(sku_id, unit_price=9999, active_quantity=5)

    response = client.get(f"/api/v1/orders/{created.json()['id']}", headers=auth_headers(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created.json()["id"]
    assert body["items"][0]["unit_price"] == 5000
    assert body["items"][0]["line_total"] == 10000
    assert body["total_amount"] == 10000


def test_other_user_order_returns_404_not_403(client, fake_b2b):
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(owner_id),
    )

    response = client.get(f"/api/v1/orders/{created.json()['id']}", headers=auth_headers(other_id))

    assert response.status_code == 404
    assert response.json()["code"] == "ORDER_NOT_FOUND"


def test_cancel_paid_order_transitions_to_cancelled(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(user_id),
    )

    response = client.post(f"/api/v1/orders/{created.json()['id']}/cancel", headers=auth_headers(user_id))

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    order = db_session.get(Order, uuid.UUID(created.json()["id"]))
    assert order.status == "CANCELLED"
    assert fake_b2b.unreserve_calls == [
        {
            "order_id": order.id,
            "items": [{"sku_id": str(sku_id), "quantity": 1}],
        }
    ]


def test_unreserve_failure_transitions_to_cancel_pending(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(user_id),
    )
    fake_b2b.fail_unreserve_unavailable = True

    response = client.post(f"/api/v1/orders/{created.json()['id']}/cancel", headers=auth_headers(user_id))

    assert response.status_code == 200
    assert response.json()["status"] == "CANCEL_PENDING"
    order = db_session.get(Order, uuid.UUID(created.json()["id"]))
    assert order.status == "CANCEL_PENDING"


def test_delivered_status_triggers_fulfill_to_b2b(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(user_id),
    )
    order = db_session.get(Order, uuid.UUID(created.json()["id"]))
    order.status = "DELIVERING"
    db_session.commit()

    response = transition_order_status(db_session, order.id, "DELIVERED", fake_b2b)

    assert response.status == "DELIVERED"
    db_session.refresh(order)
    assert order.status == "DELIVERED"
    assert fake_b2b.fulfill_calls == [
        {
            "order_id": order.id,
            "items": [{"sku_id": str(sku_id), "quantity": 1}],
        }
    ]


def test_fulfill_failure_retried_asynchronously(client, fake_b2b, db_session, caplog):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(user_id),
    )
    order = db_session.get(Order, uuid.UUID(created.json()["id"]))
    order.status = "DELIVERING"
    db_session.commit()
    fake_b2b.fail_fulfill_unavailable = True

    with caplog.at_level(logging.ERROR):
        transition_order_status(db_session, order.id, "DELIVERED", fake_b2b)

    db_session.refresh(order)
    assert order.status == "DELIVERED"
    assert "B2B fulfill failed for delivered order" in caplog.text
    assert len(fake_b2b.fulfill_calls) == 1

    fake_b2b.fail_fulfill_unavailable = False
    retried_count = retry_delivered_fulfillments(db_session, fake_b2b)

    assert retried_count == 1
    assert len(fake_b2b.fulfill_calls) == 2
    assert fake_b2b.fulfill_calls[1]["order_id"] == order.id


def test_repeated_fulfill_idempotent(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(user_id),
    )
    order = db_session.get(Order, uuid.UUID(created.json()["id"]))
    order.status = "DELIVERING"
    db_session.commit()

    transition_order_status(db_session, order.id, "DELIVERED", fake_b2b)
    transition_order_status(db_session, order.id, "DELIVERED", fake_b2b)

    assert len(fake_b2b.fulfill_calls) == 2
    assert fake_b2b.fulfill_calls[0] == fake_b2b.fulfill_calls[1]
    assert fake_b2b.fulfill_side_effects == 1


def test_cancel_assembling_order_returns_409(client, fake_b2b, db_session):
    user_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(user_id),
    )
    order = db_session.get(Order, uuid.UUID(created.json()["id"]))
    order.status = "ASSEMBLING"
    db_session.commit()

    response = client.post(f"/api/v1/orders/{order.id}/cancel", headers=auth_headers(user_id))

    assert response.status_code == 409
    assert response.json()["code"] == "CANCEL_NOT_ALLOWED"
    assert response.json()["current_status"] == "ASSEMBLING"
    db_session.refresh(order)
    assert order.status == "ASSEMBLING"
    assert fake_b2b.unreserve_calls == []


def test_other_user_order_returns_404(client, fake_b2b):
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    fake_b2b.set_sku(sku_id, active_quantity=5)
    created = client.post(
        "/api/v1/orders",
        json=_order_payload(idempotency_key, sku_id, quantity=1),
        headers=auth_headers(owner_id),
    )

    response = client.post(f"/api/v1/orders/{created.json()['id']}/cancel", headers=auth_headers(other_id))

    assert response.status_code == 404
    assert response.json()["code"] == "ORDER_NOT_FOUND"
    assert fake_b2b.unreserve_calls == []
