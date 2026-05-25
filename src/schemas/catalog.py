from __future__ import annotations

import uuid

from pydantic import BaseModel


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
