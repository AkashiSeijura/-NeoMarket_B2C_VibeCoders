from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from src.api.deps import get_required_user_id
from src.db.session import get_db
from src.schemas.order import OrderCreateRequest, OrderResponse
from src.services.b2b_client import B2BClient, get_b2b_client
from src.services.errors import EmptyOrderError, IdempotencyConflictError
from src.services.order_service import cancel_order, checkout

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(
    payload: OrderCreateRequest,
    user_id: uuid.UUID = Depends(get_required_user_id),
    idempotency_key_header: uuid.UUID | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> OrderResponse:
    idempotency_key = idempotency_key_header or payload.idempotency_key
    if idempotency_key is None:
        raise EmptyOrderError("Idempotency-Key header is required")
    if payload.idempotency_key is not None and idempotency_key_header is not None and payload.idempotency_key != idempotency_key_header:
        raise IdempotencyConflictError("Idempotency-Key header does not match request body")
    return checkout(db, user_id, payload, idempotency_key, b2b_client)


@router.post("/{order_id}/cancel", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def cancel_order_endpoint(
    order_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_required_user_id),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> OrderResponse:
    return cancel_order(db, user_id, order_id, b2b_client)
