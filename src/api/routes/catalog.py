from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from src.schemas.catalog import CatalogFacetsResponse, CatalogProductCard, CatalogProductDetail, PaginatedCatalogProducts
from src.services.b2b_client import B2BClient, get_b2b_client
from src.services.catalog_service import (
    SIMILAR_PRODUCTS_DEFAULT_LIMIT,
    get_catalog_facets,
    get_catalog_product_detail,
    get_similar_catalog_products,
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
