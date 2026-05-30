"""add banners

Revision ID: 0005_add_banners
Revises: 0004_add_product_subscriptions
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa

from src.db.types import GUID


revision = "0005_add_banners"
down_revision = "0004_add_product_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "banners",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_banners_active_schedule_priority",
        "banners",
        ["is_active", "start_at", "end_at", "priority"],
    )

    op.create_table(
        "banner_events",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("banner_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=True),
        sa.Column("event", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event IN ('impression', 'click')", name="ck_banner_events_event"),
        sa.ForeignKeyConstraint(["banner_id"], ["banners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_banner_events_banner_id", "banner_events", ["banner_id"])
    op.create_index("ix_banner_events_timestamp", "banner_events", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_banner_events_timestamp", table_name="banner_events")
    op.drop_index("ix_banner_events_banner_id", table_name="banner_events")
    op.drop_table("banner_events")
    op.drop_index("ix_banners_active_schedule_priority", table_name="banners")
    op.drop_table("banners")
