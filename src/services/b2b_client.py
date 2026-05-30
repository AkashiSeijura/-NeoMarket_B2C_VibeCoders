from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import uuid

import httpx

from src.core.config import settings
from src.services.errors import B2BRequestError, B2BUnavailableError, ReserveFailedError


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

    def fetch_catalog_products(self, params: list[tuple[str, str]]) -> dict | list:
        return self._get_json("/api/v1/products", params=params)

    def fetch_products_by_ids(self, product_ids: list[uuid.UUID]) -> list[dict]:
        if not product_ids:
            return []
        payload = self.fetch_catalog_products([("ids", ",".join(str(product_id) for product_id in product_ids))])
        if isinstance(payload, dict):
            items = payload.get("items", [])
            return items if isinstance(items, list) else []
        return payload if isinstance(payload, list) else []

    def fetch_catalog_product(self, product_id: str | uuid.UUID) -> dict:
        payload = self._get_json(f"/api/v1/products/{product_id}")
        return payload if isinstance(payload, dict) else {}

    def fetch_categories(self) -> list[dict]:
        try:
            payload = self._get_json("/api/v1/categories")
        except B2BRequestError as exc:
            if exc.status_code not in {404, 405}:
                raise
            payload = self._get_json("/api/v1/catalog/categories")
        if isinstance(payload, dict):
            items = payload.get("items", [])
            return items if isinstance(items, list) else []
        return payload if isinstance(payload, list) else []

    def fetch_category(self, category_id: str | uuid.UUID) -> dict:
        try:
            payload = self._get_json(f"/api/v1/categories/{category_id}")
        except B2BRequestError as exc:
            if exc.status_code not in {404, 405}:
                raise
            payload = self._get_json(f"/api/v1/catalog/categories/{category_id}")
        return payload if isinstance(payload, dict) else {}

    def fetch_catalog_facets(self, params: list[tuple[str, str]]) -> dict:
        try:
            payload = self._get_json("/api/v1/catalog/facets", params=params)
        except B2BRequestError as exc:
            if exc.status_code not in {404, 405}:
                raise
            catalog_params = [(key, value) for key, value in params if key not in {"limit", "offset"}]
            catalog_params.extend([("limit", "100"), ("offset", "0")])
            catalog_payload = self._get_json("/api/v1/products", params=catalog_params)
            return _facets_from_catalog_payload(catalog_payload, params)
        return payload if isinstance(payload, dict) else {"facets": []}

    def reserve(self, idempotency_key: uuid.UUID, items: list[dict]) -> None:
        headers = {"X-Service-Key": self.service_key}
        payload = {"idempotency_key": str(idempotency_key), "items": items}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/v1/reserve", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise B2BUnavailableError("B2B service unavailable") from exc

        if response.status_code >= 500:
            raise B2BUnavailableError("B2B service unavailable")
        if response.status_code == 409:
            raise ReserveFailedError(failed_items=_failed_items(response))
        if response.status_code >= 400:
            raise _b2b_request_error(response)

        data = response.json() if response.content else {}
        if isinstance(data, dict) and data.get("reserved") is False:
            raise ReserveFailedError(failed_items=data.get("failed_items") or [])

    def unreserve(self, order_id: uuid.UUID, items: list[dict]) -> None:
        headers = {"X-Service-Key": self.service_key}
        payload = {"order_id": str(order_id), "items": items}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/v1/unreserve", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise B2BUnavailableError("B2B service unavailable") from exc

        if response.status_code >= 500:
            raise B2BUnavailableError("B2B service unavailable")
        if response.status_code >= 400:
            raise _b2b_request_error(response)

        data = response.json() if response.content else {}
        if isinstance(data, dict) and data.get("unreserved") is False:
            raise B2BUnavailableError("B2B unreserve was not completed")

    def fulfill(self, order_id: uuid.UUID, items: list[dict]) -> None:
        headers = {"X-Service-Key": self.service_key}
        payload = {"order_id": str(order_id), "items": items}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/api/v1/inventory/fulfill",
                    json=payload,
                    headers=headers,
                )
                if response.status_code in {404, 405}:
                    response = client.post(f"{self.base_url}/api/v1/fulfill", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise B2BUnavailableError("B2B service unavailable") from exc

        if response.status_code >= 500:
            raise B2BUnavailableError("B2B service unavailable")
        if response.status_code >= 400:
            raise _b2b_request_error(response)

        data = response.json() if response.content else {}
        if isinstance(data, dict):
            status_value = data.get("status")
            if data.get("fulfilled") is False or data.get("ok") is False:
                raise B2BUnavailableError("B2B fulfill was not completed")
            if status_value is not None and status_value != "FULFILLED":
                raise B2BUnavailableError("B2B fulfill was not completed")

    def _get_json(self, path: str, params: list[tuple[str, str]] | None = None) -> dict | list:
        headers = {"X-Service-Key": self.service_key}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.base_url}{path}", params=params or [], headers=headers)
        except httpx.HTTPError as exc:
            raise B2BUnavailableError("B2B service unavailable") from exc

        if response.status_code >= 500:
            raise B2BUnavailableError("B2B service unavailable")
        if response.status_code >= 400:
            raise _b2b_request_error(response)
        return response.json()

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


def _b2b_request_error(response: httpx.Response) -> B2BRequestError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    code = payload.get("code") if isinstance(payload, dict) else None
    message = payload.get("message") if isinstance(payload, dict) else None
    return B2BRequestError(
        response.status_code,
        message or "B2B product service rejected request",
        code or "B2B_ERROR",
    )


def _failed_items(response: httpx.Response) -> list[dict]:
    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    failed_items = payload.get("failed_items") or []
    return failed_items if isinstance(failed_items, list) else []


def _facets_from_catalog_payload(payload: dict | list, params: list[tuple[str, str]]) -> dict:
    items = payload.get("items", []) if isinstance(payload, dict) else payload
    category_id = _last_param(params, "category_id") or _last_param(params, "filter[category_id]")
    counters: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for product in items if isinstance(items, list) else []:
        if not isinstance(product, dict):
            continue
        for key, value in (product.get("attributes") or {}).items():
            counters[str(key)][str(value)] += 1
        for characteristic in product.get("characteristics") or []:
            if isinstance(characteristic, dict) and characteristic.get("name") is not None:
                counters[_slug(str(characteristic["name"]))][str(characteristic.get("value", ""))] += 1
        for sku in product.get("skus") or []:
            for characteristic in sku.get("characteristics") or []:
                if isinstance(characteristic, dict) and characteristic.get("name") is not None:
                    counters[_slug(str(characteristic["name"]))][str(characteristic.get("value", ""))] += 1

    return {
        "category_id": category_id,
        "facets": [
            {
                "name": name,
                "values": [
                    {"value": value, "count": count}
                    for value, count in sorted(counter.items())
                ],
            }
            for name, counter in sorted(counters.items())
        ],
    }


def _last_param(params: list[tuple[str, str]], key: str) -> str | None:
    matches = [value for param_key, value in params if param_key == key]
    return matches[-1] if matches else None


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def get_b2b_client() -> B2BClient:
    return B2BClient()
