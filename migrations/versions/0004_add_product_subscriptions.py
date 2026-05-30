"""add product subscriptions

Revision ID: 0004_add_product_subscriptions
Revises: 0003_add_favorites
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa

from src.db.types import GUID


revision = "0004_add_product_subscriptions"
down_revision = "0003_add_favorites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_subscriptions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("product_id", GUID(), nullable=False),
        sa.Column("notify_on", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_product_subscriptions_user_product"),
    )
    op.create_index("ix_product_subscriptions_user_id", "product_subscriptions", ["user_id"])
    op.create_index("ix_product_subscriptions_product_id", "product_subscriptions", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_subscriptions_product_id", table_name="product_subscriptions")
    op.drop_index("ix_product_subscriptions_user_id", table_name="product_subscriptions")
    op.drop_table("product_subscriptions")
