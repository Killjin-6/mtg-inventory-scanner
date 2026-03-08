from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import URL

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

    @staticmethod
    def build_request(path: str = "/inventory/view", query: str = "") -> SimpleNamespace:
        return SimpleNamespace(url=URL(f"http://testserver{path}{'?' + query if query else ''}"))

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
        response = await routes_inventory.inventory_view(
            request=self.build_request(query="q=growth&limit=10"),
            q="growth",
            limit=10,
        )

        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn("Inventory Browser", body)
        self.assertIn("Back to /phone", body)
        self.assertIn("Beta Growth", body)
        self.assertIn("name=\"q\"", body)
        self.assertIn("/inventory/update", body)
        self.assertIn("value=\"increment\"", body)
        self.assertIn("value=\"edit\"", body)
        self.assertIn("name=\"reserved_quantity\"", body)
        self.assertIn("name=\"condition\"", body)
        self.assertIn("name=\"foil\"", body)

    async def test_inventory_update_increment_redirects_and_updates_quantity(self) -> None:
        response = await routes_inventory.inventory_update(
            scryfall_id="card-alpha",
            action="increment",
            return_to="/inventory/view?q=bolt",
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/inventory/view?q=bolt")

        with self.test_session_local() as session:
            item = session.execute(select(InventoryItem).join(CardPrinting).where(CardPrinting.scryfall_id == "card-alpha")).scalar_one()
        self.assertEqual(item.quantity, 4)

    async def test_inventory_update_decrement_deletes_row_at_one(self) -> None:
        response = await routes_inventory.inventory_update(
            scryfall_id="card-gamma",
            action="decrement",
            return_to="/inventory/view",
        )

        self.assertEqual(response.status_code, 303)

        with self.test_session_local() as session:
            item = session.execute(select(InventoryItem).join(CardPrinting).where(CardPrinting.scryfall_id == "card-gamma")).scalar_one_or_none()
        self.assertIsNone(item)

    async def test_inventory_update_remove_deletes_row(self) -> None:
        await routes_inventory.inventory_update(
            scryfall_id="card-beta",
            action="remove",
            return_to="/inventory/view",
        )

        with self.test_session_local() as session:
            item = session.execute(select(InventoryItem).join(CardPrinting).where(CardPrinting.scryfall_id == "card-beta")).scalar_one_or_none()
        self.assertIsNone(item)

    async def test_inventory_update_edit_updates_metadata(self) -> None:
        response = await routes_inventory.inventory_update(
            scryfall_id="card-alpha",
            action="edit",
            reserved_quantity=2,
            foil=1,
            condition="lp",
            return_to="/inventory/view?q=bolt",
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/inventory/view?q=bolt")

        with self.test_session_local() as session:
            item = session.execute(select(InventoryItem).join(CardPrinting).where(CardPrinting.scryfall_id == "card-alpha")).scalar_one()
        self.assertEqual(item.reserved_quantity, 2)
        self.assertEqual(item.foil, 1)
        self.assertEqual(item.condition, "LP")

    async def test_inventory_update_rejects_invalid_action(self) -> None:
        with self.assertRaises(HTTPException) as context:
            await routes_inventory.inventory_update(
                scryfall_id="card-alpha",
                action="teleport",
                return_to="/inventory/view",
            )

        self.assertEqual(context.exception.status_code, 400)

    async def test_inventory_update_rejects_negative_reserved_quantity(self) -> None:
        with self.assertRaises(HTTPException) as context:
            await routes_inventory.inventory_update(
                scryfall_id="card-alpha",
                action="edit",
                reserved_quantity=-1,
                return_to="/inventory/view",
            )

        self.assertEqual(context.exception.status_code, 400)

    async def test_inventory_update_rejects_invalid_condition(self) -> None:
        with self.assertRaises(HTTPException) as context:
            await routes_inventory.inventory_update(
                scryfall_id="card-alpha",
                action="edit",
                condition="minty",
                return_to="/inventory/view",
            )

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
