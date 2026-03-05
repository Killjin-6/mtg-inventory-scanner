from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260305_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_printing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scryfall_id", sa.String(length=64), nullable=False),
        sa.Column("oracle_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("set_code", sa.String(length=16), nullable=False),
        sa.Column("collector_number", sa.String(length=32), nullable=False),
        sa.Column("rarity", sa.String(length=32), nullable=True),
        sa.Column("color_identity", sa.Text(), nullable=True),
        sa.Column("released_at", sa.Date(), nullable=True),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("image_uri", sa.Text(), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("scryfall_id", name="uq_card_printing_scryfall_id"),
        sa.UniqueConstraint("set_code", "collector_number", "lang", name="uq_card_printing_set_collector_lang"),
    )

    op.create_table(
        "inventory_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_printing_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("condition", sa.String(length=32), nullable=True),
        sa.Column("foil", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("acquired_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["card_printing_id"], ["card_printing.id"]),
    )
    op.create_index("ix_inventory_item_card_printing_id", "inventory_item", ["card_printing_id"], unique=False)

    op.create_table(
        "scan_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column("ocr_name", sa.String(length=255), nullable=True),
        sa.Column("ocr_set_code", sa.String(length=16), nullable=True),
        sa.Column("ocr_collector_number", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("resolved_scryfall_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "sync_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("aggregate_type", sa.String(length=64), nullable=True),
        sa.Column("aggregate_key", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_sync_outbox_event_id"),
    )
    op.create_index("ix_sync_outbox_sent_at_created_at", "sync_outbox", ["sent_at", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sync_outbox_sent_at_created_at", table_name="sync_outbox")
    op.drop_table("sync_outbox")
    op.drop_table("scan_event")
    op.drop_index("ix_inventory_item_card_printing_id", table_name="inventory_item")
    op.drop_table("inventory_item")
    op.drop_table("card_printing")
