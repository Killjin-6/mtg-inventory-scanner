from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from api import routes_phone
from db.models import Base, CardPrinting, InventoryItem, ScanEvent


class ConfirmAddRouteTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_root = Path("tests") / ".tmp"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.temp_root / f"{uuid4().hex}.sqlite"
        self.engine = create_engine(f"sqlite:///{self.db_path.as_posix()}", future=True)
        Base.metadata.create_all(self.engine)
        self.test_session_local = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
            future=True,
        )
        self.original_session_local = routes_phone.SessionLocal
        routes_phone.SessionLocal = self.test_session_local

    def tearDown(self) -> None:
        routes_phone.SessionLocal = self.original_session_local
        self.engine.dispose()
        if self.db_path.exists():
            self.db_path.unlink()

    def seed_card(self, *, quantity: int | None = None) -> CardPrinting:
        with self.test_session_local() as session:
            card = CardPrinting(
                scryfall_id="card-confirm-test",
                oracle_id="oracle-confirm-test",
                name="Confirm Test Card",
                set_code="tst",
                collector_number="42",
                rarity="rare",
                color_identity="U",
                released_at=date(2024, 1, 1),
                lang="en",
                image_uri="https://example.invalid/confirm-test-card.jpg",
                last_fetched_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(card)
            session.flush()

            if quantity is not None:
                session.add(
                    InventoryItem(
                        card_printing_id=card.id,
                        quantity=quantity,
                        reserved_quantity=0,
                        foil=0,
                        condition="NM",
                    )
                )

            session.commit()
            session.refresh(card)
            return card

    async def test_confirm_add_creates_inventory_row_and_scan_event(self) -> None:
        card = self.seed_card(quantity=None)

        payload = routes_phone.ConfirmAddRequest(
            scryfall_id=card.scryfall_id,
            image_path="data/scans/raw_test.jpg",
            ocr_name="Confirm Test Card",
            ocr_set_code="tst",
            ocr_collector_number="42",
            confidence=0.97,
        )

        result = await routes_phone.confirm_add(payload)

        self.assertEqual(result["quantity"], 1)
        self.assertIn("Added Confirm Test Card", result["status"])

        with self.test_session_local() as session:
            inventory_item = session.execute(
                select(InventoryItem).where(InventoryItem.card_printing_id == card.id)
            ).scalar_one()
            scan_event = session.execute(select(ScanEvent)).scalar_one()

        self.assertEqual(inventory_item.quantity, 1)
        self.assertEqual(scan_event.resolved_scryfall_id, card.scryfall_id)
        self.assertEqual(scan_event.status, "confirmed")

    async def test_confirm_add_increments_existing_inventory_row(self) -> None:
        card = self.seed_card(quantity=2)

        payload = routes_phone.ConfirmAddRequest(
            scryfall_id=card.scryfall_id,
            image_path="data/scans/raw_test.jpg",
            ocr_name="Confirm Test Card",
            ocr_set_code="tst",
            ocr_collector_number="42",
            confidence=0.88,
        )

        result = await routes_phone.confirm_add(payload)

        self.assertEqual(result["quantity"], 3)

        with self.test_session_local() as session:
            inventory_item = session.execute(
                select(InventoryItem).where(InventoryItem.card_printing_id == card.id)
            ).scalar_one()
            events = session.execute(select(ScanEvent)).scalars().all()

        self.assertEqual(inventory_item.quantity, 3)
        self.assertEqual(len(events), 1)

    async def test_confirm_add_raises_404_for_missing_card(self) -> None:
        payload = routes_phone.ConfirmAddRequest(scryfall_id="missing-card")

        with self.assertRaises(HTTPException) as context:
            await routes_phone.confirm_add(payload)

        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
