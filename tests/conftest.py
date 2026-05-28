from __future__ import annotations

from collections.abc import Generator
import base64
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_required_user_id
from src.db.base import Base
from src.db.session import get_db
from src.main import app
from src.services.b2b_client import B2BSku, get_b2b_client


class FakeB2BClient:
    def __init__(self):
        self.skus: dict[uuid.UUID, B2BSku] = {}
        self.catalog_products: list[dict] = []
        self.catalog_product: dict | None = None
        self.fail_catalog = False
        self.fail_reserve_unavailable = False
        self.fail_unreserve_unavailable = False
        self.reserve_failed_items: list[dict] = []
        self.reserve_calls: list[dict] = []
        self.unreserve_calls: list[dict] = []
        self.catalog_calls: list[list[tuple[str, str]]] = []

    def set_sku(
        self,
        sku_id: uuid.UUID,
        *,
        product_id: uuid.UUID | None = None,
        product_title: str = "Phone",
        sku_name: str = "Black",
        unit_price: int = 1000,
        active_quantity: int = 10,
        product_status: str = "MODERATED",
    ) -> B2BSku:
        sku = B2BSku(
            id=sku_id,
            product_id=product_id or uuid.uuid4(),
            product_title=product_title,
            sku_name=sku_name,
            unit_price=unit_price,
            active_quantity=active_quantity,
            image_url="/img/product.jpg",
            product_status=product_status,
        )
        self.skus[sku_id] = sku
        return sku

    def fetch_skus(self, sku_ids: list[uuid.UUID]) -> dict[uuid.UUID, B2BSku]:
        if self.fail_catalog:
            from src.services.errors import B2BUnavailableError

            raise B2BUnavailableError("B2B service unavailable")
        return {sku_id: self.skus[sku_id] for sku_id in sku_ids if sku_id in self.skus}

    def reserve(self, idempotency_key: uuid.UUID, items: list[dict]) -> None:
        if self.fail_reserve_unavailable:
            from src.services.errors import B2BUnavailableError

            raise B2BUnavailableError("B2B service unavailable")
        self.reserve_calls.append({"idempotency_key": idempotency_key, "items": items})
        if self.reserve_failed_items:
            from src.services.errors import ReserveFailedError

            raise ReserveFailedError(failed_items=self.reserve_failed_items)

    def unreserve(self, order_id: uuid.UUID, items: list[dict]) -> None:
        self.unreserve_calls.append({"order_id": order_id, "items": items})
        if self.fail_unreserve_unavailable:
            from src.services.errors import B2BUnavailableError

            raise B2BUnavailableError("B2B service unavailable")

    def fetch_catalog_products(self, params: list[tuple[str, str]]) -> dict:
        if self.fail_catalog:
            from src.services.errors import B2BUnavailableError

            raise B2BUnavailableError("B2B service unavailable")
        self.catalog_calls.append(params)
        params_map = _params_map(params)
        products = list(self.catalog_products)

        category_id = params_map.get("category_id") or params_map.get("filter[category_id]")
        if category_id:
            products = [item for item in products if item.get("category_id") == category_id]

        query = params_map.get("q")
        if query:
            lowered = query.lower()
            products = [
                item
                for item in products
                if lowered in (item.get("name") or item.get("title") or "").lower()
            ]

        for key, value in params:
            if key.startswith("filters[") and key.endswith("]"):
                slug = key.removeprefix("filters[").removesuffix("]")
                products = [item for item in products if _attribute(item, slug) == value]
            if key.startswith("filter[attributes][") and key.endswith("]"):
                slug = key.removeprefix("filter[attributes][").removesuffix("]")
                products = [item for item in products if _attribute(item, slug) == value]

        sort = params_map.get("sort", "popularity")
        if sort == "price_asc":
            products.sort(key=_catalog_price)
        elif sort == "price_desc":
            products.sort(key=_catalog_price, reverse=True)
        elif sort == "new":
            products.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        else:
            products.sort(key=lambda item: item.get("popularity", 0), reverse=True)

        limit = int(params_map.get("limit", 20))
        offset = int(params_map.get("offset", 0))
        return {
            "items": products[offset : offset + limit],
            "total_count": len(products),
            "limit": limit,
            "offset": offset,
        }

    def fetch_catalog_product(self, product_id: str) -> dict:
        if self.fail_catalog:
            from src.services.errors import B2BUnavailableError

            raise B2BUnavailableError("B2B service unavailable")
        if self.catalog_product is not None:
            return self.catalog_product
        for product in self.catalog_products:
            if str(product.get("id")) == str(product_id):
                return product
        from src.services.errors import NotFoundError

        raise NotFoundError("Product not found")

    def fetch_catalog_facets(self, params: list[tuple[str, str]]) -> dict:
        if self.fail_catalog:
            from src.services.errors import B2BUnavailableError

            raise B2BUnavailableError("B2B service unavailable")
        self.catalog_calls.append(params)
        params_map = _params_map(params)
        category_id = params_map.get("category_id") or params_map.get("filter[category_id]")
        products = [
            item
            for item in self.catalog_products
            if not category_id or item.get("category_id") == category_id
        ]
        counts: dict[str, dict[str, int]] = {}
        for product in products:
            for key, value in (product.get("attributes") or {}).items():
                counts.setdefault(key, {})
                counts[key][str(value)] = counts[key].get(str(value), 0) + 1
        return {
            "category_id": category_id,
            "facets": [
                {
                    "name": key,
                    "values": [
                        {"value": value, "count": count}
                        for value, count in sorted(values.items())
                    ],
                }
                for key, values in sorted(counts.items())
            ],
        }


def _params_map(params: list[tuple[str, str]]) -> dict[str, str]:
    result = {}
    for key, value in params:
        result[key] = value
    return result


def _attribute(product: dict, slug: str) -> str | None:
    attributes = product.get("attributes") or {}
    return attributes.get(slug) or product.get(slug)


def _catalog_price(product: dict) -> int:
    return int(product.get("min_price", product.get("price", 0)))


@pytest.fixture()
def fake_b2b() -> FakeB2BClient:
    return FakeB2BClient()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        yield session

    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: Session, fake_b2b: FakeB2BClient) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_b2b_client] = lambda: fake_b2b

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def jwt_for(user_id: uuid.UUID) -> str:
    header = _b64url({"alg": "none", "typ": "JWT"})
    payload = _b64url({"sub": str(user_id)})
    return f"{header}.{payload}."


def auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_for(user_id)}"}


def _b64url(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")
