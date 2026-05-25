from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from src.api.deps import get_cart_identity, get_required_session_id, get_required_user_id
from src.db.session import get_db
from src.schemas.cart import (
    AddCartItemRequest,
    CartItemRead,
    CartMutationResponse,
    CartResponse,
    UpdateCartItemRequest,
)
from src.services.b2b_client import B2BClient, get_b2b_client
from src.services.cart_service import (
    CartIdentity,
    add_item,
    clear_cart,
    delete_item,
    get_cart,
    get_cart_item,
    merge_guest_cart,
    update_item,
)

router = APIRouter(prefix="/api/v1/cart", tags=["Cart"])


@router.get("", response_model=CartResponse)
def get_cart_endpoint(
    identity: CartIdentity = Depends(get_cart_identity),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CartResponse:
    return get_cart(db, identity, b2b_client)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart_endpoint(
    identity: CartIdentity = Depends(get_cart_identity),
    db: Session = Depends(get_db),
) -> Response:
    clear_cart(db, identity)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items", response_model=CartMutationResponse)
def add_cart_item_endpoint(
    payload: AddCartItemRequest,
    response: Response,
    identity: CartIdentity = Depends(get_cart_identity),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CartMutationResponse:
    result, status_code = add_item(db, identity, payload.sku_id, payload.quantity, b2b_client)
    response.status_code = status_code
    return result


@router.get("/items/{item_id}", response_model=CartItemRead)
def get_cart_item_endpoint(
    item_id: uuid.UUID,
    identity: CartIdentity = Depends(get_cart_identity),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CartItemRead:
    return get_cart_item(db, identity, item_id, b2b_client)


@router.put("/items/{item_id}", response_model=CartMutationResponse)
def update_cart_item_endpoint(
    item_id: uuid.UUID,
    payload: UpdateCartItemRequest,
    identity: CartIdentity = Depends(get_cart_identity),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CartMutationResponse:
    return update_item(db, identity, item_id, payload.quantity, b2b_client)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item_endpoint(
    item_id: uuid.UUID,
    identity: CartIdentity = Depends(get_cart_identity),
    db: Session = Depends(get_db),
) -> Response:
    delete_item(db, identity, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/merge", response_model=CartResponse)
def merge_cart_endpoint(
    user_id: uuid.UUID = Depends(get_required_user_id),
    session_id: str = Depends(get_required_session_id),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> CartResponse:
    return merge_guest_cart(db, user_id, session_id, b2b_client)
