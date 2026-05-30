"""add collections

Revision ID: 0006_add_collections
Revises: 0005_add_banners
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa

from src.db.types import GUID


revision = "0006_add_collections"
down_revision = "0005_add_banners"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_image_url", sa.String(length=500), nullable=True),
        sa.Column("target_url", sa.String(length=500), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collections_active_start_priority",
        "collections",
        ["is_active", "start_date", "priority"],
    )

    op.create_table(
        "collection_products",
        sa.Column("collection_id", GUID(), nullable=False),
        sa.Column("product_id", GUID(), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("collection_id", "product_id"),
    )
    op.create_index(
        "ix_collection_products_collection_ordering",
        "collection_products",
        ["collection_id", "ordering"],
    )


def downgrade() -> None:
    op.drop_index("ix_collection_products_collection_ordering", table_name="collection_products")
    op.drop_table("collection_products")
    op.drop_index("ix_collections_active_start_priority", table_name="collections")
    op.drop_table("collections")
