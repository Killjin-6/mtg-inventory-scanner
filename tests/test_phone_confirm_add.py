from __future__ import annotations

from io import BytesIO
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException, UploadFile
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
        self.scans_dir = self.temp_root / f"scans_{uuid4().hex}"
        self.scans_dir.mkdir(parents=True, exist_ok=True)
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
        self.original_scans_dir = routes_phone.SCANS_DIR
        routes_phone.SessionLocal = self.test_session_local
        routes_phone.SCANS_DIR = self.scans_dir

    def tearDown(self) -> None:
        routes_phone.SessionLocal = self.original_session_local
        routes_phone.SCANS_DIR = self.original_scans_dir
        self.engine.dispose()
        if self.db_path.exists():
            self.db_path.unlink()
        for path in self.scans_dir.glob("*"):
            if path.is_file():
                path.unlink()
        if self.scans_dir.exists():
            self.scans_dir.rmdir()

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

    async def test_confirm_add_updates_existing_scan_event_when_id_provided(self) -> None:
        card = self.seed_card(quantity=None)

        with self.test_session_local() as session:
            scan_event = ScanEvent(
                image_path="data/scans/raw_before.jpg",
                ocr_name="Before",
                ocr_set_code="old",
                ocr_collector_number="1",
                confidence=0.11,
                resolved_scryfall_id=None,
                status="captured_unresolved",
            )
            session.add(scan_event)
            session.commit()
            session.refresh(scan_event)
            scan_event_id = scan_event.id

        payload = routes_phone.ConfirmAddRequest(
            scan_event_id=scan_event_id,
            scryfall_id=card.scryfall_id,
            image_path="data/scans/raw_test.jpg",
            ocr_name="Confirm Test Card",
            ocr_set_code="tst",
            ocr_collector_number="42",
            confidence=0.88,
        )

        result = await routes_phone.confirm_add(payload)

        self.assertEqual(result["scan_event_id"], scan_event_id)

        with self.test_session_local() as session:
            events = session.execute(select(ScanEvent)).scalars().all()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, "confirmed")
        self.assertEqual(events[0].resolved_scryfall_id, card.scryfall_id)

    async def test_confirm_add_raises_404_for_missing_card(self) -> None:
        payload = routes_phone.ConfirmAddRequest(scryfall_id="missing-card")

        with self.assertRaises(HTTPException) as context:
            await routes_phone.confirm_add(payload)

        self.assertEqual(context.exception.status_code, 404)

    async def test_capture_upload_creates_scan_event(self) -> None:
        image = BytesIO()
        from PIL import Image

        Image.new("RGB", (8, 8), color="white").save(image, format="JPEG")
        image.seek(0)
        upload = UploadFile(filename="test.jpg", file=image)

        with patch.object(routes_phone, "cv2", None), patch.object(
            routes_phone, "ocr_availability_message", return_value="OCR unavailable for test."
        ), patch.object(
            routes_phone,
            "resolve_card_printing",
            return_value={"status": "unresolved", "match_type": "none", "card": None, "candidates": []},
        ):
            result = await routes_phone.capture_upload(upload)

        self.assertIn("scan_event_id", result)
        self.assertEqual(result["resolution"]["status"], "unresolved")

        with self.test_session_local() as session:
            event = session.execute(select(ScanEvent)).scalar_one()

        self.assertEqual(event.id, result["scan_event_id"])
        self.assertEqual(event.status, "captured_unresolved")
        self.assertEqual(event.image_path, result["used_image_path"])

    async def test_scan_history_returns_recent_events_first(self) -> None:
        with self.test_session_local() as session:
            session.add_all(
                [
                    ScanEvent(status="captured_unresolved", ocr_name="Older Scan"),
                    ScanEvent(status="confirmed", ocr_name="Newer Scan", resolved_scryfall_id="card-confirm-test"),
                ]
            )
            session.commit()

        history = await routes_phone.scan_history(limit=10)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["ocr_name"], "Newer Scan")
        self.assertEqual(history[1]["ocr_name"], "Older Scan")
        self.assertEqual(history[0]["status"], "confirmed")
        self.assertIsNotNone(history[0]["captured_at"])

    async def test_phone_page_contains_history_drawer_ui(self) -> None:
        response = await routes_phone.phone_page()

        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn("Recent Scans", body)
        self.assertIn("history-drawer", body)
        self.assertIn("/scan-history?limit=20", body)


if __name__ == "__main__":
    unittest.main()
