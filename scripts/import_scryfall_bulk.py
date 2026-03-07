from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from db.init_db import run_migrations
from db.models import CardPrinting
from db.repo import create_engine_for_path

SCRYFALL_BULK_URL = "https://api.scryfall.com/bulk-data"
DEFAULT_BULK_TYPE = "default_cards"
DEFAULT_DOWNLOAD_DIR = Path("data") / "scryfall"
DEFAULT_DB_PATH = Path("data") / "local.sqlite"
USER_AGENT = "mtg-card-scanner/0.1 (+local bulk importer)"
ACCEPT = "application/json;q=0.9,*/*;q=0.8"
BATCH_SIZE = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Scryfall bulk card data into the local SQLite catalog.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help="Directory used to store downloaded Scryfall bulk files.",
    )
    parser.add_argument(
        "--bulk-type",
        default=DEFAULT_BULK_TYPE,
        help="Scryfall bulk data type to fetch. default_cards is recommended for print-level matching.",
    )
    parser.add_argument(
        "--source-file",
        type=Path,
        default=None,
        help="Optional local bulk JSON file to import instead of downloading from Scryfall.",
    )
    parser.add_argument(
        "--all-languages",
        action="store_true",
        help="Import every language instead of filtering to English printings only.",
    )
    return parser.parse_args()


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": ACCEPT})
    with urlopen(request) as response:
        return json.load(response)


def download_file(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": ACCEPT})
    with urlopen(request) as response, destination.open("wb") as output:
        output.write(response.read())
    return destination


def choose_bulk_item(metadata: dict[str, Any], bulk_type: str) -> dict[str, Any]:
    data = metadata.get("data", [])
    for item in data:
        if item.get("type") == bulk_type:
            return item
    raise RuntimeError(f"Scryfall bulk type '{bulk_type}' was not found.")


def ensure_bulk_file(download_dir: Path, bulk_type: str) -> Path:
    metadata = fetch_json(SCRYFALL_BULK_URL)
    bulk_item = choose_bulk_item(metadata, bulk_type)
    updated_at = str(bulk_item.get("updated_at", "unknown")).replace(":", "-")
    destination = download_dir / f"{bulk_type}_{updated_at}.json"
    if destination.exists():
        print(f"Using cached bulk file: {destination}")
        return destination

    download_uri = bulk_item.get("download_uri")
    if not download_uri:
        raise RuntimeError(f"Scryfall bulk item '{bulk_type}' did not include a download_uri.")

    print(f"Downloading {bulk_type} from Scryfall...")
    return download_file(download_uri, destination)


def load_bulk_cards(source_file: Path) -> list[dict[str, Any]]:
    with source_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise RuntimeError(f"Expected a JSON array of card objects in {source_file}.")
    return payload


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def stringify_color_identity(values: list[str] | None) -> str | None:
    if not values:
        return None
    return ",".join(values)


def preferred_image_uri(card: dict[str, Any]) -> str | None:
    image_uris = card.get("image_uris")
    if isinstance(image_uris, dict):
        return image_uris.get("normal") or image_uris.get("large") or image_uris.get("small")

    card_faces = card.get("card_faces")
    if isinstance(card_faces, list):
        for face in card_faces:
            face_uris = face.get("image_uris")
            if isinstance(face_uris, dict):
                return face_uris.get("normal") or face_uris.get("large") or face_uris.get("small")
    return None


def build_row(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "scryfall_id": card["id"],
        "oracle_id": card.get("oracle_id"),
        "name": card["name"],
        "set_code": str(card["set"]).lower(),
        "collector_number": str(card["collector_number"]),
        "rarity": card.get("rarity"),
        "color_identity": stringify_color_identity(card.get("color_identity")),
        "released_at": parse_date(card.get("released_at")),
        "lang": card.get("lang", "en"),
        "image_uri": preferred_image_uri(card),
        "last_fetched_at": datetime.utcnow(),
    }


def should_import(card: dict[str, Any], import_all_languages: bool) -> bool:
    if "id" not in card or "name" not in card or "set" not in card or "collector_number" not in card:
        return False
    if import_all_languages:
        return True
    return card.get("lang", "en") == "en"


def row_priority(card: dict[str, Any]) -> tuple[int, int, int]:
    return (
        1 if card.get("digital") else 0,
        0 if preferred_image_uri(card) else 1,
        0 if card.get("promo") else 1,
    )


def deduplicate_cards(cards: list[dict[str, Any]], import_all_languages: bool) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for card in cards:
        if not should_import(card, import_all_languages):
            continue

        key = (
            str(card["set"]).lower(),
            str(card["collector_number"]),
            str(card.get("lang", "en")),
        )

        existing = deduped.get(key)
        if existing is None or row_priority(card) < row_priority(existing):
            deduped[key] = card

    return list(deduped.values())


def batched_rows(cards: list[dict[str, Any]], import_all_languages: bool) -> list[list[dict[str, Any]]]:
    unique_cards = deduplicate_cards(cards, import_all_languages)
    rows: list[list[dict[str, Any]]] = []
    batch: list[dict[str, Any]] = []
    for card in unique_cards:
        batch.append(build_row(card))
        if len(batch) >= BATCH_SIZE:
            rows.append(batch)
            batch = []
    if batch:
        rows.append(batch)
    return rows


def upsert_batches(session: Session, row_batches: list[list[dict[str, Any]]]) -> int:
    imported = 0
    for batch in row_batches:
        statement = insert(CardPrinting).values(batch)
        upsert = statement.on_conflict_do_update(
            index_elements=[CardPrinting.set_code, CardPrinting.collector_number, CardPrinting.lang],
            set_={
                "scryfall_id": statement.excluded.scryfall_id,
                "oracle_id": statement.excluded.oracle_id,
                "name": statement.excluded.name,
                "set_code": statement.excluded.set_code,
                "collector_number": statement.excluded.collector_number,
                "rarity": statement.excluded.rarity,
                "color_identity": statement.excluded.color_identity,
                "released_at": statement.excluded.released_at,
                "lang": statement.excluded.lang,
                "image_uri": statement.excluded.image_uri,
                "last_fetched_at": statement.excluded.last_fetched_at,
            },
        )
        session.execute(upsert)
        session.commit()
        imported += len(batch)
        print(f"Imported {imported} rows...")
    return imported


def main() -> None:
    args = parse_args()
    run_migrations(args.db_path)

    source_file = args.source_file
    if source_file is None:
        source_file = ensure_bulk_file(args.download_dir, args.bulk_type)
    else:
        source_file = source_file.resolve()

    print(f"Loading bulk file: {source_file}")
    cards = load_bulk_cards(source_file)
    print(f"Loaded {len(cards)} card objects from bulk file.")

    row_batches = batched_rows(cards, args.all_languages)
    if not row_batches:
        print("No card rows matched the import filter.")
        return

    engine = create_engine_for_path(args.db_path)
    with Session(engine) as session:
        imported = upsert_batches(session, row_batches)

    language_scope = "all languages" if args.all_languages else "English only"
    print(f"Finished importing {imported} printings ({language_scope}).")


if __name__ == "__main__":
    main()
