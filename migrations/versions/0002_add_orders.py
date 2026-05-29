"""add orders

Revision ID: 0002_add_orders
Revises: 0001_initial_cart
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa

from src.db.types import GUID


revision = "0002_add_orders"
down_revision = "0001_initial_cart"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("buyer_id", GUID(), nullable=False),
        sa.Column("idempotency_key", GUID(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("subtotal", sa.Integer(), nullable=False),
        sa.Column("delivery_cost", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("address_id", GUID(), nullable=True),
        sa.Column("payment_method_id", GUID(), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_non_negative"),
        sa.CheckConstraint("delivery_cost >= 0", name="ck_orders_delivery_cost_non_negative"),
        sa.CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
    )
    op.create_index("ix_orders_buyer_id", "orders", ["buyer_id"])

    op.create_table(
        "order_items",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("order_id", GUID(), nullable=False),
        sa.Column("sku_id", GUID(), nullable=False),
        sa.Column("product_id", GUID(), nullable=False),
        sa.Column("product_title", sa.String(length=500), nullable=False),
        sa.Column("sku_name", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_order_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
        sa.CheckConstraint("line_total >= 0", name="ck_order_items_line_total_non_negative"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_sku_id", "order_items", ["sku_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_sku_id", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_buyer_id", table_name="orders")
    op.drop_table("orders")
