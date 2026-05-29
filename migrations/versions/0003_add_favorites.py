"""add favorites

Revision ID: 0003_add_favorites
Revises: 0002_add_orders
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa

from src.db.types import GUID


revision = "0003_add_favorites"
down_revision = "0002_add_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("product_id", GUID(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),
    )
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
    op.create_index("ix_favorites_product_id", "favorites", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_favorites_product_id", table_name="favorites")
    op.drop_index("ix_favorites_user_id", table_name="favorites")
    op.drop_table("favorites")
