from __future__ import annotations

from dataclasses import dataclass
import uuid

import httpx

from src.core.config import settings
from src.services.errors import B2BUnavailableError


@dataclass(frozen=True)
class B2BSku:
    id: uuid.UUID
    product_id: uuid.UUID
    product_title: str
    sku_name: str
    unit_price: int
    active_quantity: int
    image_url: str | None = None
    product_status: str = "MODERATED"
    sku_enabled: bool = True


class B2BClient:
    def __init__(
        self,
        base_url: str = settings.b2b_url,
        service_key: str = settings.b2c_to_b2b_key,
        timeout: float = settings.b2b_timeout_seconds,
    ):
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self.timeout = timeout

    def fetch_skus(self, sku_ids: list[uuid.UUID]) -> dict[uuid.UUID, B2BSku]:
        if not sku_ids:
            return {}

        products = self._fetch_products_by_sku_ids(sku_ids)
        return _index_skus(products, sku_ids)

    def _fetch_products_by_sku_ids(self, sku_ids: list[uuid.UUID]) -> list[dict]:
        headers = {"X-Service-Key": self.service_key}
        sku_param = ",".join(str(sku_id) for sku_id in sku_ids)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/api/v1/public/products",
                    params={"sku_ids": sku_param, "limit": 100},
                    headers=headers,
                )
                if response.status_code in {404, 405, 422}:
                    response = client.get(
                        f"{self.base_url}/api/v1/public/products",
                        params={"limit": 100},
                        headers=headers,
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise B2BUnavailableError("B2B service unavailable") from exc

        payload = response.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            items = payload.get("items", [])
            return items if isinstance(items, list) else []
        return []


def _index_skus(products: list[dict], requested_ids: list[uuid.UUID]) -> dict[uuid.UUID, B2BSku]:
    requested = set(requested_ids)
    result: dict[uuid.UUID, B2BSku] = {}

    for product in products:
        product_id = _as_uuid(product.get("id"))
        if product_id is None:
            continue

        product_images = product.get("images") or []
        product_image_url = _first_image_url(product_images)
        product_status = str(product.get("status") or "MODERATED")
        product_title = str(product.get("title") or product.get("name") or "")

        for raw_sku in product.get("skus") or []:
            sku_id = _as_uuid(raw_sku.get("id"))
            if sku_id is None or sku_id not in requested:
                continue

            sku_images = raw_sku.get("images") or []
            result[sku_id] = B2BSku(
                id=sku_id,
                product_id=product_id,
                product_title=product_title,
                sku_name=str(raw_sku.get("name") or raw_sku.get("article") or ""),
                unit_price=int(raw_sku.get("price") or raw_sku.get("unit_price") or 0),
                active_quantity=int(
                    raw_sku.get("active_quantity")
                    if raw_sku.get("active_quantity") is not None
                    else raw_sku.get("activeQuantity")
                    if raw_sku.get("activeQuantity") is not None
                    else raw_sku.get("available_quantity")
                    or 0
                ),
                image_url=_first_image_url(sku_images) or str(raw_sku.get("image") or "") or product_image_url,
                product_status=product_status,
                sku_enabled=not bool(raw_sku.get("deleted") or raw_sku.get("disabled")),
            )

    return result


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _first_image_url(images) -> str | None:
    if not images:
        return None
    first = images[0]
    if isinstance(first, dict):
        return first.get("url")
    return str(first)


def get_b2b_client() -> B2BClient:
    return B2BClient()

