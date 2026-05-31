"""require order address and payment method

Revision ID: 0008_require_order_address_payment
Revises: 0007_add_product_event_idempotency
Create Date: 2026-05-31
"""

from alembic import op

from src.db.types import GUID


revision = "0008_require_order_address_payment"
down_revision = "0007_add_product_event_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE orders SET address_id = id WHERE address_id IS NULL")
    op.execute("UPDATE orders SET payment_method_id = id WHERE payment_method_id IS NULL")
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column("address_id", existing_type=GUID(), nullable=False)
        batch_op.alter_column("payment_method_id", existing_type=GUID(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column("payment_method_id", existing_type=GUID(), nullable=True)
        batch_op.alter_column("address_id", existing_type=GUID(), nullable=True)
