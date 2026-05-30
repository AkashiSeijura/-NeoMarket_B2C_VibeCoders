from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import require_service_key
from src.db.session import get_db
from src.schemas.events import B2BProductEventRequest, EventAcceptedResponse, ProductEventRequest
from src.services.event_service import handle_product_event, sku_ids_from_openapi_payload

router = APIRouter(tags=["B2B Events"])


@router.post("/api/v1/events/product", response_model=EventAcceptedResponse)
def product_event_endpoint(
    payload: ProductEventRequest,
    _: None = Depends(require_service_key),
    db: Session = Depends(get_db),
) -> EventAcceptedResponse:
    handle_product_event(
        db,
        idempotency_key=payload.idempotency_key,
        event_type=payload.event,
        product_id=payload.product_id,
        sku_ids=payload.sku_ids,
    )
    return EventAcceptedResponse()


@router.post("/api/v1/b2b/events", response_model=EventAcceptedResponse)
def b2b_event_endpoint(
    payload: B2BProductEventRequest,
    _: None = Depends(require_service_key),
    db: Session = Depends(get_db),
) -> EventAcceptedResponse:
    product_id = uuid.UUID(str(payload.payload["product_id"]))
    handle_product_event(
        db,
        idempotency_key=payload.idempotency_key,
        event_type=payload.event_type,
        product_id=product_id,
        sku_ids=sku_ids_from_openapi_payload(payload.event_type, payload.payload),
    )
    return EventAcceptedResponse()
