from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ImageRef(BaseModel):
    id: str
    url: str
    ordering: int = 0
    alt: str | None = None
    is_main: bool | None = None


class CategoryRef(BaseModel):
    id: uuid.UUID | str
    name: str | None = None
    parent_id: uuid.UUID | str | None = None
    level: int | None = None
    path: list[str] | None = None
    slug: str | None = None


class CategoryTreeNode(CategoryRef):
    children: list["CategoryTreeNode"] = Field(default_factory=list)


class CategoryTreeResponse(BaseModel):
    items: list[CategoryTreeNode]


class CategoryParentRef(BaseModel):
    id: uuid.UUID | str
    name: str
    slug: str | None = None


class CategorySeo(BaseModel):
    title: str | None = None
    description: str | None = None
    keywords: list[str] | None = None


class CategoryDetail(BaseModel):
    id: uuid.UUID | str
    name: str
    slug: str | None = None
    description: str | None = None
    parent: CategoryParentRef | None = None
    product_count: int | None = None
    seo: CategorySeo | dict | None = None
    meta_tags: dict | None = None
    image_url: str | None = None
    is_active: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None


class BreadcrumbItem(BaseModel):
    id: uuid.UUID | str
    slug: str | None = None
    name: str
    url: str
    level: int
    is_current: bool


class BreadcrumbMeta(BaseModel):
    resolved_via: str
    category_id: uuid.UUID | str
    product_id: uuid.UUID | str | None = None


class BreadcrumbsResponse(BaseModel):
    data: list[BreadcrumbItem]
    meta: BreadcrumbMeta


class CatalogProductCard(BaseModel):
    id: uuid.UUID | str
    name: str
    min_price: int
    has_stock: bool
    images: list[ImageRef]
    slug: str | None = None
    category: CategoryRef | dict | None = None
    old_price: int | None = None
    rating: float | None = None
    reviews_count: int | None = None
    seller: dict | None = None


class CatalogSku(BaseModel):
    id: uuid.UUID | str
    price: int
    available_quantity: int
    name: str | None = None
    sku_code: str | None = None
    old_price: int | None = None
    attributes: dict | None = None
    images: list[ImageRef] = []


class CatalogProductDetail(CatalogProductCard):
    description: str
    attributes: dict | None = None
    skus: list[CatalogSku]


class PaginatedCatalogProducts(BaseModel):
    items: list[CatalogProductCard]
    total_count: int
    limit: int
    offset: int


class FacetValue(BaseModel):
    value: str
    count: int


class Facet(BaseModel):
    name: str
    values: list[FacetValue]


class CatalogFacetsResponse(BaseModel):
    category_id: uuid.UUID | str | None = None
    facets: list[Facet]
