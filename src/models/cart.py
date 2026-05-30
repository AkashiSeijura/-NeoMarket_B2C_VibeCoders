from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.db.types import GUID
from src.models.base import TimestampMixin, utcnow


class CartItem(TimestampMixin, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_cart_items_quantity_positive"),
        CheckConstraint(
            "user_id IS NOT NULL OR session_id IS NOT NULL",
            name="ck_cart_items_identity_present",
        ),
        Index("ix_cart_items_user_id", "user_id"),
        Index("ix_cart_items_session_id", "session_id"),
        Index("ix_cart_items_sku_id", "sku_id"),
        UniqueConstraint("user_id", "sku_id", name="uq_cart_items_user_sku"),
        UniqueConstraint("session_id", "sku_id", name="uq_cart_items_session_sku"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unavailable_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class EventIdempotencyKey(TimestampMixin, Base):
    __tablename__ = "event_idempotency_keys"
    __table_args__ = (
        Index("ix_event_idempotency_keys_event_type", "event_type"),
        Index("ix_event_idempotency_keys_product_id", "product_id"),
    )

    idempotency_key: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        Index("ix_favorites_user_id", "user_id"),
        Index("ix_favorites_product_id", "product_id"),
        UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProductSubscription(TimestampMixin, Base):
    __tablename__ = "product_subscriptions"
    __table_args__ = (
        Index("ix_product_subscriptions_user_id", "user_id"),
        Index("ix_product_subscriptions_product_id", "product_id"),
        UniqueConstraint("user_id", "product_id", name="uq_product_subscriptions_user_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    notify_on: Mapped[list[str]] = mapped_column(JSON, nullable=False)
