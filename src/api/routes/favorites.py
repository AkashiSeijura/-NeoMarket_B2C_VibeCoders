from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from src.api.deps import get_jwt_user_id
from src.db.session import get_db
from src.schemas.catalog import PaginatedCatalogProducts
from src.schemas.favorites import FavoriteResponse
from src.services.b2b_client import B2BClient, get_b2b_client
from src.services.favorite_service import add_favorite, delete_favorite, list_favorites, put_favorite

router = APIRouter(prefix="/api/v1/favorites", tags=["Favorites"])


@router.get("", response_model=PaginatedCatalogProducts)
def get_favorites_endpoint(
    user_id: uuid.UUID = Depends(get_jwt_user_id),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> PaginatedCatalogProducts:
    return list_favorites(db, user_id, b2b_client, limit=limit, offset=offset)


@router.post("/{product_id}", response_model=FavoriteResponse, include_in_schema=False)
def post_favorite_endpoint(
    product_id: uuid.UUID,
    response: Response,
    user_id: uuid.UUID = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> FavoriteResponse:
    favorite, status_code = add_favorite(db, user_id, product_id, b2b_client)
    response.status_code = status_code
    return favorite


@router.put("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def put_favorite_endpoint(
    product_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> Response:
    put_favorite(db, user_id, product_id, b2b_client)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_favorite_endpoint(
    product_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
) -> Response:
    delete_favorite(db, user_id, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
