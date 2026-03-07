from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from db.init_db import main as init_db
from db.models import CardPrinting, InventoryItem
from db.repo import SessionLocal


def main() -> None:
    init_db()

    with SessionLocal() as session:
        card = session.execute(
            select(CardPrinting).where(CardPrinting.scryfall_id == "dummy-scryfall-id")
        ).scalar_one_or_none()

        if card is None:
            card = session.execute(
                select(CardPrinting).where(
                    CardPrinting.set_code == "lea",
                    CardPrinting.collector_number == "161",
                    CardPrinting.lang == "en",
                )
            ).scalar_one_or_none()

        if card is None:
            card = CardPrinting(
                scryfall_id="dummy-scryfall-id",
                oracle_id="dummy-oracle-id",
                name="Lightning Bolt",
                set_code="lea",
                collector_number="161",
                rarity="common",
                color_identity='["R"]',
                released_at=datetime(1993, 8, 5).date(),
                lang="en",
                image_uri="https://example.invalid/lightning-bolt.jpg",
                last_fetched_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(card)
            session.flush()

        item = session.execute(
            select(InventoryItem).where(InventoryItem.card_printing_id == card.id)
        ).scalar_one_or_none()

        if item is None:
            item = InventoryItem(
                card_printing_id=card.id,
                quantity=3,
                reserved_quantity=1,
                condition="NM",
                foil=0,
                acquired_at=datetime.now(UTC).replace(tzinfo=None),
                notes="smoke test row",
            )
            session.add(item)
            session.commit()

        quantity = session.execute(
            select(InventoryItem.quantity).where(InventoryItem.card_printing_id == card.id)
        ).scalar_one()
        print(quantity)


if __name__ == "__main__":
    main()
