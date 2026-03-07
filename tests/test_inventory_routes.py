from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api import routes_inventory
from db.models import Base, CardPrinting, InventoryItem


class InventoryRoutesTest(unittest.IsolatedAsyncioTestCase):
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
        self.original_session_local = routes_inventory.SessionLocal
        routes_inventory.SessionLocal = self.test_session_local

        with self.test_session_local() as session:
            alpha = CardPrinting(
                scryfall_id="card-alpha",
                oracle_id="oracle-alpha",
                name="Alpha Bolt",
                set_code="lea",
                collector_number="161",
                rarity="common",
                color_identity="R",
                released_at=date(1993, 8, 5),
                lang="en",
                image_uri="https://example.invalid/alpha-bolt.jpg",
                last_fetched_at=datetime.now(UTC).replace(tzinfo=None),
            )
            beta = CardPrinting(
                scryfall_id="card-beta",
                oracle_id="oracle-beta",
                name="Beta Growth",
                set_code="ice",
                collector_number="244",
                rarity="uncommon",
                color_identity="G",
                released_at=date(1995, 6, 3),
                lang="en",
                image_uri="https://example.invalid/beta-growth.jpg",
                last_fetched_at=datetime.now(UTC).replace(tzinfo=None),
            )
            gamma = CardPrinting(
                scryfall_id="card-gamma",
                oracle_id="oracle-gamma",
                name="Gamma Counter",
                set_code="usg",
                collector_number="77",
                rarity="rare",
                color_identity="U",
                released_at=date(1998, 10, 12),
                lang="en",
                image_uri="https://example.invalid/gamma-counter.jpg",
                last_fetched_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add_all([alpha, beta, gamma])
            session.flush()

            session.add_all(
                [
                    InventoryItem(
                        card_printing_id=alpha.id,
                        quantity=3,
                        reserved_quantity=1,
                        foil=0,
                        condition="NM",
                    ),
                    InventoryItem(
                        card_printing_id=beta.id,
                        quantity=2,
                        reserved_quantity=0,
                        foil=1,
                        condition="LP",
                    ),
                    InventoryItem(
                        card_printing_id=gamma.id,
                        quantity=1,
                        reserved_quantity=0,
                        foil=0,
                        condition="NM",
                    ),
                ]
            )
            session.commit()

    def tearDown(self) -> None:
        routes_inventory.SessionLocal = self.original_session_local
        self.engine.dispose()
        if self.db_path.exists():
            self.db_path.unlink()

    async def test_inventory_rows_returns_newest_first_with_expected_fields(self) -> None:
        rows = await routes_inventory.inventory_rows(limit=10)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["name"], "Gamma Counter")
        self.assertEqual(rows[1]["name"], "Beta Growth")
        self.assertEqual(rows[2]["name"], "Alpha Bolt")
        self.assertEqual(
            set(rows[0].keys()),
            {
                "name",
                "set_code",
                "collector_number",
                "rarity",
                "color_identity",
                "quantity",
                "reserved_quantity",
                "foil",
                "condition",
                "scryfall_id",
                "image_uri",
            },
        )

    async def test_inventory_rows_applies_filters(self) -> None:
        rows = await routes_inventory.inventory_rows(q="bolt", color="R", rarity="common", set="lea", limit=10)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alpha Bolt")
        self.assertEqual(rows[0]["quantity"], 3)

    async def test_inventory_view_renders_expected_content(self) -> None:
        response = await routes_inventory.inventory_view(q="growth", limit=10)

        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn("Inventory Browser", body)
        self.assertIn("Back to /phone", body)
        self.assertIn("Beta Growth", body)
        self.assertIn("name=\"q\"", body)


if __name__ == "__main__":
    unittest.main()
