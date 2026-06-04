from __future__ import annotations

import uuid

import httpx

import src.services.b2b_client as b2b_module
from src.services.b2b_client import B2BClient


def test_b2b_client_reserve_uses_inventory_contract_path(monkeypatch):
    captured = {}

    class FakeHttpClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return httpx.Response(200, json={"reserved": True})

    monkeypatch.setattr(b2b_module.httpx, "Client", FakeHttpClient)

    idempotency_key = uuid.uuid4()
    sku_id = uuid.uuid4()
    B2BClient(base_url="http://b2b:8000", service_key="secret-key").reserve(
        idempotency_key,
        [{"sku_id": str(sku_id), "quantity": 1}],
    )

    assert captured["url"] == "http://b2b:8000/api/v1/inventory/reserve"
    assert captured["json"] == {
        "idempotency_key": str(idempotency_key),
        "items": [{"sku_id": str(sku_id), "quantity": 1}],
    }
    assert captured["headers"]["X-Service-Key"] == "secret-key"


def test_b2b_client_unreserve_uses_inventory_contract_path(monkeypatch):
    captured = {}

    class FakeHttpClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return httpx.Response(200, json={"unreserved": True})

    monkeypatch.setattr(b2b_module.httpx, "Client", FakeHttpClient)

    order_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    B2BClient(base_url="http://b2b:8000", service_key="secret-key").unreserve(
        order_id,
        [{"sku_id": str(sku_id), "quantity": 1}],
    )

    assert captured["url"] == "http://b2b:8000/api/v1/inventory/unreserve"
    assert captured["json"] == {
        "order_id": str(order_id),
        "items": [{"sku_id": str(sku_id), "quantity": 1}],
    }
    assert captured["headers"]["X-Service-Key"] == "secret-key"
