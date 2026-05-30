from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_jwt_user_id, require_service_key
from src.db.session import get_db
from src.schemas.order import (
    OrderCreateRequest,
    OrderResponse,
    OrderStatusUpdateRequest,
    PaginatedOrders,
)
from src.services.b2b_client import B2BClient, get_b2b_client
from src.services.errors import EmptyOrderError, IdempotencyConflictError
from src.services.order_service import (
    cancel_order,
    checkout,
    get_order,
    list_orders,
    transition_order_status,
)

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])

OrderStatusFilter = Literal[
    "CREATED",
    "PAID",
    "ASSEMBLING",
    "DELIVERING",
    "DELIVERED",
    "CANCELLED",
    "CANCEL_PENDING",
]


@router.get("", response_model=PaginatedOrders, status_code=status.HTTP_200_OK)
def list_orders_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    order_status: OrderStatusFilter | None = Query(default=None, alias="status"),
    user_id: uuid.UUID = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
) -> PaginatedOrders:
    return list_orders(db, user_id, limit=limit, offset=offset, status=order_status)


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(
    payload: OrderCreateRequest,
    user_id: uuid.UUID = Depends(get_jwt_user_id),
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


@router.get("/{order_id}", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def get_order_endpoint(
    order_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
) -> OrderResponse:
    return get_order(db, user_id, order_id)


@router.post("/{order_id}/cancel", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def cancel_order_endpoint(
    order_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> OrderResponse:
    return cancel_order(db, user_id, order_id, b2b_client)


@router.post(
    "/{order_id}/status",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def update_order_status_endpoint(
    order_id: uuid.UUID,
    payload: OrderStatusUpdateRequest,
    _: None = Depends(require_service_key),
    db: Session = Depends(get_db),
    b2b_client: B2BClient = Depends(get_b2b_client),
) -> OrderResponse:
    return transition_order_status(db, order_id, payload.status, b2b_client)
