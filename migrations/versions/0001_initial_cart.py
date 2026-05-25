"""initial cart schema

Revision ID: 0001_initial_cart
Revises:
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa

from src.db.types import GUID


revision = "0001_initial_cart"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cart_items",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("sku_id", GUID(), nullable=False),
        sa.Column("product_id", GUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_cart_items_quantity_positive"),
        sa.CheckConstraint(
            "user_id IS NOT NULL OR session_id IS NOT NULL",
            name="ck_cart_items_identity_present",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sku_id", name="uq_cart_items_user_sku"),
        sa.UniqueConstraint("session_id", "sku_id", name="uq_cart_items_session_sku"),
    )
    op.create_index("ix_cart_items_user_id", "cart_items", ["user_id"])
    op.create_index("ix_cart_items_session_id", "cart_items", ["session_id"])
    op.create_index("ix_cart_items_sku_id", "cart_items", ["sku_id"])


def downgrade() -> None:
    op.drop_index("ix_cart_items_sku_id", table_name="cart_items")
    op.drop_index("ix_cart_items_session_id", table_name="cart_items")
    op.drop_index("ix_cart_items_user_id", table_name="cart_items")
    op.drop_table("cart_items")
