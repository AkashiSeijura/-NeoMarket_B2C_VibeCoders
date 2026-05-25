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
        return {sku_id: self.skus[sku_id] for sku_id in sku_ids if sku_id in self.skus}


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

