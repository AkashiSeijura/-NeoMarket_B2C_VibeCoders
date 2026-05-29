from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

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
from src.services.b2b_client import B2BClient, get_b2b_client
from src.services.catalog_service import (
    SIMILAR_PRODUCTS_DEFAULT_LIMIT,
    get_breadcrumbs,
    get_catalog_facets,
    get_catalog_product_detail,
    get_category_detail,
    get_category_tree,
    get_category_tree_response,
    get_similar_catalog_products,
    list_categories,
    list_catalog_products,
)

router = APIRouter(tags=["Catalog"])

CATALOG_PRODUCTS_OPENAPI_EXTRA = {
    "parameters": [
        {
            "name": "filter",
            "in": "query",
            "style": "deepObject",
            "explode": True,
            "schema": {
                "type": "object",
                "properties": {
                    "category_id": {"type": "string", "format": "uuid"},
                    "price_min": {"type": "integer", "minimum": 0},
                    "price_max": {"type": "integer", "minimum": 0},
                    "seller_id": {"type": "string", "format": "uuid"},
                    "attributes": {"type": "object", "additionalProperties": True},
                },
            },
        }
    ]
}

@router.get(
    "/api/v1/catalog/products",
    response_model=PaginatedCatalogProducts,
    openapi_extra=CATALOG_PRODUCTS_OPENAPI_EXTRA,
)
@router.get("/api/v1/products", response_model=PaginatedCatalogProducts, include_in_schema=False)
def list_products_endpoint(
    request: Request,
    limit: int = Query(default=20),
    offset: int = Query(default=0),
    sort: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    search: str | None = Query(default=None, include_in_schema=False),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> PaginatedCatalogProducts:
    return list_catalog_products(
        b2b_client,
        request.query_params,
        limit=limit,
        offset=offset,
        sort=sort,
        q=q,
        search=search,
    )


@router.get("/api/v1/catalog/categories", response_model=list[CategoryRef])
def list_categories_endpoint(
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> list[CategoryRef]:
    return list_categories(b2b_client)


@router.get("/api/v1/catalog/categories/tree", response_model=list[CategoryTreeNode])
def category_tree_endpoint(
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> list[CategoryTreeNode]:
    return get_category_tree(b2b_client)


@router.get("/api/v1/categories", response_model=CategoryTreeResponse, include_in_schema=False)
def category_tree_flow_endpoint(
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CategoryTreeResponse:
    return get_category_tree_response(b2b_client)


@router.get("/api/v1/catalog/categories/{category_id}", response_model=CategoryDetail)
@router.get("/api/v1/categories/{category_id}", response_model=CategoryDetail, include_in_schema=False)
def category_detail_endpoint(
    category_id: str,
    include_product_count: bool = Query(default=False),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CategoryDetail:
    return get_category_detail(b2b_client, category_id, include_product_count=include_product_count)


@router.get("/api/v1/breadcrumbs", response_model=BreadcrumbsResponse)
def breadcrumbs_endpoint(
    category_id: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> BreadcrumbsResponse:
    return get_breadcrumbs(b2b_client, category_id=category_id, product_id=product_id)


@router.get("/api/v1/catalog/products/{product_id}", response_model=CatalogProductDetail)
@router.get("/api/v1/products/{product_id}", response_model=CatalogProductDetail, include_in_schema=False)
def product_detail_endpoint(
    product_id: str,
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CatalogProductDetail:
    return get_catalog_product_detail(b2b_client, product_id)


@router.get("/api/v1/catalog/products/{product_id}/similar", response_model=list[CatalogProductCard])
@router.get("/api/v1/products/{product_id}/similar", response_model=list[CatalogProductCard], include_in_schema=False)
def similar_products_endpoint(
    product_id: str,
    limit: int = Query(default=SIMILAR_PRODUCTS_DEFAULT_LIMIT, ge=1, le=50),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> list[CatalogProductCard]:
    return get_similar_catalog_products(b2b_client, product_id, limit=limit)


@router.get("/api/v1/catalog/facets", response_model=CatalogFacetsResponse)
def catalog_facets_endpoint(
    request: Request,
    category_id: str | None = Query(default=None),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CatalogFacetsResponse:
    return get_catalog_facets(b2b_client, request.query_params, category_id=category_id)
