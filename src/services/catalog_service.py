from __future__ import annotations

from collections.abc import Iterable

from starlette.datastructures import QueryParams

from src.schemas.catalog import CatalogFacetsResponse, PaginatedCatalogProducts
from src.services.b2b_client import B2BClient
from src.services.errors import InvalidSortError


ALLOWED_SORTS = ("price_asc", "price_desc", "popularity", "new")
DEFAULT_SORT = "popularity"


def list_catalog_products(
    b2b_client: B2BClient,
    query_params: QueryParams,
    *,
    limit: int,
    offset: int,
    sort: str | None,
    q: str | None,
    search: str | None,
) -> PaginatedCatalogProducts:
    normalized_limit = _clamp(limit, 1, 100)
    normalized_offset = max(offset, 0)
    normalized_sort = sort or DEFAULT_SORT
    _validate_sort(normalized_sort)
    normalized_q = q if q is not None else search

    params = _catalog_query_params(
        query_params.multi_items(),
        limit=normalized_limit,
        offset=normalized_offset,
        sort=normalized_sort,
        q=normalized_q,
    )
    payload = b2b_client.fetch_catalog_products(params)
    return PaginatedCatalogProducts.model_validate(_normalize_catalog_page(payload, normalized_limit, normalized_offset))


def get_catalog_facets(
    b2b_client: B2BClient,
    query_params: QueryParams,
    *,
    category_id: str | None,
) -> CatalogFacetsResponse:
    params = _catalog_query_params(query_params.multi_items(), passthrough_pagination=True)
    payload = b2b_client.fetch_catalog_facets(params)
    if "category_id" not in payload and category_id is not None:
        payload = {**payload, "category_id": category_id}
    return CatalogFacetsResponse.model_validate(payload)


def _validate_sort(sort: str) -> None:
    if sort not in ALLOWED_SORTS:
        raise InvalidSortError(f"Invalid sort parameter. Allowed values: {', '.join(ALLOWED_SORTS)}")


def _catalog_query_params(
    raw_items: Iterable[tuple[str, str]],
    *,
    limit: int | None = None,
    offset: int | None = None,
    sort: str | None = None,
    q: str | None = None,
    passthrough_pagination: bool = False,
) -> list[tuple[str, str]]:
    items = list(raw_items)
    normalized: list[tuple[str, str]] = []
    skip_keys = {"limit", "offset", "sort", "q", "search"}
    if passthrough_pagination:
        skip_keys = set()

    existing_keys = {key for key, _ in items}
    for key, value in items:
        if key in skip_keys:
            continue
        normalized.append((key, value))
        if key == "category_id" and "filter[category_id]" not in existing_keys:
            normalized.append(("filter[category_id]", value))
        if key.startswith("filters[") and key.endswith("]"):
            slug = key.removeprefix("filters[").removesuffix("]")
            target = f"filter[attributes][{slug}]"
            if target not in existing_keys:
                normalized.append((target, value))

    if limit is not None:
        normalized.append(("limit", str(limit)))
    if offset is not None:
        normalized.append(("offset", str(offset)))
    if sort is not None:
        normalized.append(("sort", sort))
    if q:
        normalized.append(("q", q))
    return normalized


def _normalize_catalog_page(payload: dict | list, limit: int, offset: int) -> dict:
    if isinstance(payload, list):
        items = payload
        total_count = len(items)
        response_limit = limit
        response_offset = offset
    else:
        items = payload.get("items", [])
        total_count = int(payload.get("total_count", len(items)))
        response_limit = int(payload.get("limit", limit))
        response_offset = int(payload.get("offset", offset))

    normalized_items = [_normalize_catalog_item(item) for item in items]
    return {
        "items": normalized_items,
        "total_count": total_count,
        "limit": response_limit,
        "offset": response_offset,
    }


def _normalize_catalog_item(item: dict) -> dict:
    skus = item.get("skus") or []
    prices = [
        int(sku.get("price_cents", sku.get("price")))
        for sku in skus
        if sku.get("price_cents", sku.get("price")) is not None
    ]
    quantities = [
        int(sku.get("available_quantity", sku.get("active_quantity", sku.get("quantity", 0))))
        for sku in skus
    ]
    images = item.get("images")
    if not images and item.get("image"):
        images = [item["image"]]
    if not images and item.get("cover_image"):
        images = [item["cover_image"]]

    return {
        "id": item.get("id"),
        "slug": item.get("slug"),
        "name": item.get("name") or item.get("title") or "",
        "category": item.get("category") or ({"id": item["category_id"]} if item.get("category_id") else None),
        "min_price": int(item.get("min_price", item.get("price", min(prices) if prices else 0))),
        "old_price": item.get("old_price"),
        "has_stock": bool(item.get("has_stock", item.get("in_stock", any(quantity > 0 for quantity in quantities)))),
        "rating": item.get("rating"),
        "reviews_count": item.get("reviews_count"),
        "images": _normalize_images(images),
        "seller": item.get("seller"),
    }


def _normalize_images(images: list[dict | str] | None) -> list[dict]:
    normalized = []
    for index, image in enumerate(images or []):
        if isinstance(image, str):
            normalized.append({"id": image, "url": image, "ordering": index})
            continue
        image_data = dict(image)
        if "ordering" not in image_data and "order" in image_data:
            image_data["ordering"] = image_data.pop("order")
        image_data.setdefault("ordering", index)
        image_data.setdefault("id", image_data.get("url", f"image-{index}"))
        normalized.append(image_data)
    return normalized


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return min(max(value, minimum), maximum)
