"""add product event idempotency

Revision ID: 0007_add_product_event_idempotency
Revises: 0006_add_collections
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa

from src.db.types import GUID


revision = "0007_add_product_event_idempotency"
down_revision = "0006_add_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cart_items", sa.Column("unavailable_reason", sa.String(length=64), nullable=True))
    op.create_table(
        "event_idempotency_keys",
        sa.Column("idempotency_key", GUID(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("product_id", GUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_event_idempotency_keys_event_type",
        "event_idempotency_keys",
        ["event_type"],
    )
    op.create_index(
        "ix_event_idempotency_keys_product_id",
        "event_idempotency_keys",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_idempotency_keys_product_id", table_name="event_idempotency_keys")
    op.drop_index("ix_event_idempotency_keys_event_type", table_name="event_idempotency_keys")
    op.drop_table("event_idempotency_keys")
    op.drop_column("cart_items", "unavailable_reason")
