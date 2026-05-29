from __future__ import annotations

from collections.abc import Iterable

from starlette.datastructures import QueryParams

from src.schemas.catalog import (
    BreadcrumbsResponse,
    CatalogFacetsResponse,
    CatalogProductCard,
    CatalogProductDetail,
    CategoryDetail,
    CategoryRef,
    CategoryTreeNode,
    CategoryTreeResponse,
    PaginatedCatalogProducts,
)
from src.services.b2b_client import B2BClient
from src.services.errors import (
    BreadcrumbParamError,
    CategoryHierarchyError,
    InvalidSearchQueryError,
    InvalidSortError,
    NotFoundError,
)


ALLOWED_SORTS = ("price_asc", "price_desc", "popularity", "new")
DEFAULT_SORT = "popularity"
SIMILAR_PRODUCTS_DEFAULT_LIMIT = 8


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
    normalized_query = _normalize_search_query(q if q is not None else search)
    search_param_name = "q" if q is not None else "search"

    params = _catalog_query_params(
        query_params.multi_items(),
        limit=normalized_limit,
        offset=normalized_offset,
        sort=normalized_sort,
        search_name=search_param_name,
        search_value=normalized_query,
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


def list_categories(b2b_client: B2BClient) -> list[CategoryRef]:
    return [CategoryRef.model_validate(category) for category in _normalized_categories(b2b_client)]


def get_category_tree(b2b_client: B2BClient) -> list[CategoryTreeNode]:
    categories = _normalized_categories(b2b_client)
    return [CategoryTreeNode.model_validate(node) for node in _build_category_tree(categories)]


def get_category_tree_response(b2b_client: B2BClient) -> CategoryTreeResponse:
    return CategoryTreeResponse(items=get_category_tree(b2b_client))


def get_category_detail(
    b2b_client: B2BClient,
    category_id: str,
    *,
    include_product_count: bool = False,
) -> CategoryDetail:
    categories = _normalized_categories(b2b_client)
    index = _category_index(categories)
    category = index.get(str(category_id))
    if category is None:
        raise NotFoundError("Category not found")
    _category_path(categories, str(category_id))

    parent = None
    parent_id = category.get("parent_id")
    if parent_id is not None:
        parent_category = index[str(parent_id)]
        parent = {
            "id": parent_category["id"],
            "name": parent_category["name"],
            "slug": parent_category.get("slug"),
        }

    payload = {
        **category,
        "description": category.get("description"),
        "parent": parent,
        "seo": category.get("seo"),
        "meta_tags": category.get("meta_tags"),
        "image_url": category.get("image_url"),
        "is_active": category.get("is_active"),
        "created_at": category.get("created_at"),
        "updated_at": category.get("updated_at"),
    }
    if include_product_count:
        payload["product_count"] = _category_product_count(b2b_client, category_id)
    elif "product_count" in category:
        payload["product_count"] = category["product_count"]

    return CategoryDetail.model_validate(payload)


def get_breadcrumbs(
    b2b_client: B2BClient,
    *,
    category_id: str | None,
    product_id: str | None,
) -> BreadcrumbsResponse:
    if category_id and product_id:
        raise BreadcrumbParamError("ambiguous_param", "only one of category_id or product_id must be provided")
    if not category_id and not product_id:
        raise BreadcrumbParamError("missing_param", "category_id or product_id must be provided")

    resolved_via = "category_id"
    resolved_category_id = category_id
    if product_id:
        product = b2b_client.fetch_catalog_product(product_id)
        if _is_hidden_product(product):
            raise NotFoundError("Product not found")
        resolved_category_id = _product_category_id(product)
        resolved_via = "product_id"
        if resolved_category_id is None:
            raise CategoryHierarchyError()

    categories = _normalized_categories(b2b_client)
    path = _category_path(categories, str(resolved_category_id))
    url_parts: list[str] = []
    data = []
    for level, category in enumerate(path):
        url_parts.append(str(category.get("slug") or category["id"]))
        data.append(
            {
                "id": category["id"],
                "slug": category.get("slug"),
                "name": category["name"],
                "url": f"/catalog/{'/'.join(url_parts)}",
                "level": level,
                "is_current": level == len(path) - 1,
            }
        )

    return BreadcrumbsResponse.model_validate(
        {
            "data": data,
            "meta": {
                "resolved_via": resolved_via,
                "category_id": str(resolved_category_id),
                "product_id": product_id,
            },
        }
    )


def get_catalog_product_detail(b2b_client: B2BClient, product_id: str) -> CatalogProductDetail:
    payload = b2b_client.fetch_catalog_product(product_id)
    if _is_hidden_product(payload):
        raise NotFoundError("Product not found")
    return CatalogProductDetail.model_validate(_normalize_product_detail(payload))


def get_similar_catalog_products(
    b2b_client: B2BClient,
    product_id: str,
    *,
    limit: int = SIMILAR_PRODUCTS_DEFAULT_LIMIT,
) -> list[CatalogProductCard]:
    current_product = b2b_client.fetch_catalog_product(product_id)
    if _is_hidden_product(current_product):
        raise NotFoundError("Product not found")

    category_id = _product_category_id(current_product)
    if category_id is None:
        return []

    normalized_limit = _clamp(limit, 1, 50)
    products = _similar_products_from_category(
        b2b_client,
        category_id,
        product_id=product_id,
        limit=normalized_limit,
    )

    parent_category_id = _product_parent_category_id(current_product)
    if len(products) < normalized_limit and parent_category_id is not None:
        products.extend(
            _similar_products_from_category(
                b2b_client,
                parent_category_id,
                product_id=product_id,
                limit=normalized_limit - len(products),
                seen_ids={str(item["id"]) for item in products},
            )
        )

    return [CatalogProductCard.model_validate(_normalize_catalog_item(product)) for product in products[:normalized_limit]]


def _validate_sort(sort: str) -> None:
    if sort not in ALLOWED_SORTS:
        raise InvalidSortError(f"Invalid sort parameter. Allowed values: {', '.join(ALLOWED_SORTS)}")


def _normalized_categories(b2b_client: B2BClient) -> list[dict]:
    return [_normalize_category(category) for category in b2b_client.fetch_categories()]


def _normalize_category(category: dict) -> dict:
    name = str(category.get("name") or category.get("title") or "")
    slug = category.get("slug") or _slug(name) or str(category.get("id"))
    payload = {
        **category,
        "id": str(category.get("id")),
        "name": name,
        "parent_id": str(category["parent_id"]) if category.get("parent_id") is not None else None,
        "slug": slug,
    }
    if payload.get("level") is not None:
        payload["level"] = int(payload["level"])
    if payload.get("path") is not None:
        payload["path"] = [str(item) for item in payload["path"]]
    return payload


def _category_index(categories: list[dict]) -> dict[str, dict]:
    return {str(category["id"]): category for category in categories}


def _build_category_tree(categories: list[dict]) -> list[dict]:
    index = _category_index(categories)
    nodes = [{**category, "children": []} for category in categories]
    node_index = {str(node["id"]): node for node in nodes}
    roots: list[dict] = []

    for node in nodes:
        parent_id = node.get("parent_id")
        if parent_id is None:
            roots.append(node)
            continue
        if str(parent_id) not in index or str(parent_id) == str(node["id"]):
            raise CategoryHierarchyError()
        node_index[str(parent_id)]["children"].append(node)

    _detect_category_cycles(categories)
    _assign_category_levels(roots, level=0, path=[])
    return roots


def _category_path(categories: list[dict], category_id: str) -> list[dict]:
    index = _category_index(categories)
    category = index.get(str(category_id))
    if category is None:
        raise NotFoundError("Category not found")

    path = []
    seen: set[str] = set()
    current = category
    while current is not None:
        current_id = str(current["id"])
        if current_id in seen:
            raise CategoryHierarchyError()
        seen.add(current_id)
        path.append(current)
        parent_id = current.get("parent_id")
        if parent_id is None:
            break
        parent = index.get(str(parent_id))
        if parent is None:
            raise CategoryHierarchyError()
        current = parent
    return list(reversed(path))


def _detect_category_cycles(categories: list[dict]) -> None:
    index = _category_index(categories)
    for category in categories:
        seen: set[str] = set()
        current = category
        while current.get("parent_id") is not None:
            current_id = str(current["id"])
            if current_id in seen:
                raise CategoryHierarchyError()
            seen.add(current_id)
            current = index.get(str(current["parent_id"]))
            if current is None:
                raise CategoryHierarchyError()


def _assign_category_levels(nodes: list[dict], *, level: int, path: list[str]) -> None:
    for node in nodes:
        node["level"] = level
        node["path"] = [*path, node["name"]]
        _assign_category_levels(node["children"], level=level + 1, path=node["path"])


def _category_product_count(b2b_client: B2BClient, category_id: str) -> int:
    payload = b2b_client.fetch_catalog_products(
        [("filter[category_id]", str(category_id)), ("limit", "1"), ("offset", "0")]
    )
    if isinstance(payload, dict):
        return int(payload.get("total_count", len(payload.get("items", []))))
    return len(payload) if isinstance(payload, list) else 0


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _normalize_search_query(query: str | None) -> str | None:
    if query is None:
        return None

    normalized = query.strip()
    if len(normalized) < 3:
        raise InvalidSearchQueryError("Search query must be at least 3 characters")
    if len(normalized) > 255:
        raise InvalidSearchQueryError("Search query must be at most 255 characters")
    return normalized


def _catalog_query_params(
    raw_items: Iterable[tuple[str, str]],
    *,
    limit: int | None = None,
    offset: int | None = None,
    sort: str | None = None,
    search_name: str = "q",
    search_value: str | None = None,
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
    if search_value:
        normalized.append((search_name, search_value))
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


def _normalize_product_detail(product: dict) -> dict:
    skus = [_normalize_sku(sku) for sku in product.get("skus") or []]
    card = _normalize_catalog_item(product)
    min_price, old_price, has_stock = _aggregate_skus(skus, card["min_price"], card["has_stock"])
    card["min_price"] = min_price
    card["has_stock"] = has_stock
    if old_price is not None:
        card["old_price"] = old_price
    elif "old_price" in card:
        card.pop("old_price")
    card.update(
        {
            "description": product.get("description") or "",
            "attributes": _attributes(product.get("attributes"), product.get("characteristics")),
            "skus": skus,
        }
    )
    return card


def _similar_products_from_category(
    b2b_client: B2BClient,
    category_id: str,
    *,
    product_id: str,
    limit: int,
    seen_ids: set[str] | None = None,
) -> list[dict]:
    seen = set(seen_ids or set())
    seen.add(str(product_id))
    payload = b2b_client.fetch_catalog_products(
        [
            ("filter[category_id]", category_id),
            ("limit", str(min(limit + len(seen), 100))),
            ("offset", "0"),
            ("sort", DEFAULT_SORT),
        ]
    )
    items = payload.get("items", []) if isinstance(payload, dict) else payload
    products: list[dict] = []
    for item in items if isinstance(items, list) else []:
        item_id = str(item.get("id"))
        if item_id in seen:
            continue
        seen.add(item_id)
        products.append(item)
        if len(products) >= limit:
            break
    return products


def _product_category_id(product: dict) -> str | None:
    if product.get("category_id") is not None:
        return str(product["category_id"])
    category = product.get("category")
    if isinstance(category, dict) and category.get("id") is not None:
        return str(category["id"])
    return None


def _product_parent_category_id(product: dict) -> str | None:
    category = product.get("category")
    if isinstance(category, dict):
        if category.get("parent_id") is not None:
            return str(category["parent_id"])
        parent = category.get("parent")
        if isinstance(parent, dict) and parent.get("id") is not None:
            return str(parent["id"])
    if product.get("parent_category_id") is not None:
        return str(product["parent_category_id"])
    return None


def _normalize_sku(sku: dict) -> dict:
    price = int(sku.get("price_cents", sku.get("price", 0)) or 0)
    discount = _non_negative_int(sku.get("discount", 0))
    current_price = max(0, price - discount) if discount > 0 else price
    available_quantity = _non_negative_int(
        sku.get("available_quantity", sku.get("active_quantity", sku.get("quantity", 0)))
    )
    payload = {
        "id": sku.get("id"),
        "name": sku.get("name"),
        "sku_code": sku.get("sku_code") or sku.get("article"),
        "price": current_price,
        "available_quantity": available_quantity,
        "attributes": _attributes(sku.get("attributes"), sku.get("characteristics")),
        "images": _normalize_images(sku.get("images") or ([sku["image"]] if sku.get("image") else [])),
    }
    if discount > 0:
        payload["old_price"] = price
    return payload


def _aggregate_skus(skus: list[dict], fallback_price: int, fallback_stock: bool) -> tuple[int, int | None, bool]:
    if not skus:
        return fallback_price, None, fallback_stock

    available = [sku for sku in skus if sku["available_quantity"] > 0]
    pool = available or skus
    min_sku = min(pool, key=lambda sku: sku["price"])
    return min_sku["price"], min_sku.get("old_price"), bool(available)


def _attributes(raw_attributes, characteristics) -> dict:
    if isinstance(raw_attributes, dict):
        return dict(raw_attributes)
    result = {}
    for row in characteristics or []:
        if isinstance(row, dict) and row.get("name") is not None:
            result[str(row["name"])] = row.get("value")
    return result


def _is_hidden_product(product: dict) -> bool:
    return (
        not product
        or product.get("status") != "MODERATED"
        or bool(product.get("deleted", product.get("is_deleted", False)))
        or bool(product.get("blocked", product.get("is_blocked", False)))
    )


def _non_negative_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
