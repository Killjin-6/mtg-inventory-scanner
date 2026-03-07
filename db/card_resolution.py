from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import CardPrinting


def normalize_set_code(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def normalize_collector_number(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-zA-Z0-9]", "", text)


def normalize_name(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.strip().split())


def serialize_card_printing(card: CardPrinting | None) -> dict[str, Any] | None:
    if card is None:
        return None

    return {
        "scryfall_id": card.scryfall_id,
        "name": card.name,
        "set_code": card.set_code,
        "collector_number": card.collector_number,
        "rarity": card.rarity,
        "color_identity": card.color_identity,
        "image_uri": card.image_uri,
        "lang": card.lang,
    }


def resolve_card_printing(
    session: Session,
    *,
    set_code: str | None,
    collector_number: str | None,
    name: str | None,
    lang: str = "en",
    candidate_limit: int = 5,
) -> dict[str, Any]:
    normalized_set_code = normalize_set_code(set_code)
    normalized_collector_number = normalize_collector_number(collector_number)
    normalized_name = normalize_name(name)

    if normalized_set_code and normalized_collector_number:
        exact_stmt = (
            select(CardPrinting)
            .where(CardPrinting.set_code == normalized_set_code)
            .where(CardPrinting.collector_number == normalized_collector_number)
            .where(CardPrinting.lang == lang)
            .limit(1)
        )
        exact_match = session.execute(exact_stmt).scalar_one_or_none()
        if exact_match is not None:
            return {
                "status": "exact_match",
                "match_type": "set+number",
                "card": serialize_card_printing(exact_match),
                "candidates": [],
            }

    if normalized_collector_number and normalized_name:
        fallback_stmt = (
            select(CardPrinting)
            .where(CardPrinting.collector_number == normalized_collector_number)
            .where(CardPrinting.lang == lang)
            .where(func.lower(CardPrinting.name).like(f"%{normalized_name.lower()}%"))
            .limit(candidate_limit)
        )
        fallback_matches = list(session.execute(fallback_stmt).scalars())
        if fallback_matches:
            return {
                "status": "fallback_match",
                "match_type": "number+name",
                "card": serialize_card_printing(fallback_matches[0]),
                "candidates": [serialize_card_printing(card) for card in fallback_matches],
            }

    if normalized_name:
        name_only_stmt = (
            select(CardPrinting)
            .where(CardPrinting.lang == lang)
            .where(func.lower(CardPrinting.name).like(f"%{normalized_name.lower()}%"))
            .limit(candidate_limit)
        )
        name_matches = list(session.execute(name_only_stmt).scalars())
        if name_matches:
            return {
                "status": "fallback_match",
                "match_type": "name_only",
                "card": serialize_card_printing(name_matches[0]),
                "candidates": [serialize_card_printing(card) for card in name_matches],
                "needs_review": True,
            }

    return {
        "status": "unresolved",
        "match_type": "none",
        "card": None,
        "candidates": [],
    }
