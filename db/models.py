from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CardPrinting(Base):
    __tablename__ = "card_printing"
    __table_args__ = (
        UniqueConstraint("scryfall_id", name="uq_card_printing_scryfall_id"),
        UniqueConstraint("set_code", "collector_number", "lang", name="uq_card_printing_set_collector_lang"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scryfall_id: Mapped[str] = mapped_column(String(64), nullable=False)
    oracle_id: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    set_code: Mapped[str] = mapped_column(String(16), nullable=False)
    collector_number: Mapped[str] = mapped_column(String(32), nullable=False)
    rarity: Mapped[str | None] = mapped_column(String(32))
    color_identity: Mapped[str | None] = mapped_column(Text)
    released_at: Mapped[date | None] = mapped_column(Date)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    image_uri: Mapped[str | None] = mapped_column(Text)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    inventory_items: Mapped[list["InventoryItem"]] = relationship(back_populates="card_printing")


class InventoryItem(Base):
    __tablename__ = "inventory_item"
    __table_args__ = (Index("ix_inventory_item_card_printing_id", "card_printing_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_printing_id: Mapped[int] = mapped_column(ForeignKey("card_printing.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    condition: Mapped[str | None] = mapped_column(String(32))
    foil: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    notes: Mapped[str | None] = mapped_column(Text)

    card_printing: Mapped[CardPrinting] = relationship(back_populates="inventory_items")


class ScanEvent(Base):
    __tablename__ = "scan_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utc_now_naive, server_default=func.now()
    )
    image_path: Mapped[str | None] = mapped_column(Text)
    ocr_name: Mapped[str | None] = mapped_column(String(255))
    ocr_set_code: Mapped[str | None] = mapped_column(String(16))
    ocr_collector_number: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Float)
    resolved_scryfall_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(32))


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_sync_outbox_event_id"),
        Index("ix_sync_outbox_sent_at_created_at", "sent_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str | None] = mapped_column(String(64))
    aggregate_type: Mapped[str | None] = mapped_column(String(64))
    aggregate_key: Mapped[str | None] = mapped_column(String(128))
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utc_now_naive, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
