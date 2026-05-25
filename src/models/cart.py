from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.db.types import GUID
from src.models.base import TimestampMixin


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
