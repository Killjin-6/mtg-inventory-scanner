from __future__ import annotations

from difflib import SequenceMatcher
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
    compact = re.sub(r"\s+", "", text)
    if "/" in compact:
        compact = compact.split("/", 1)[0]
    return re.sub(r"[^a-zA-Z0-9]", "", compact)


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


def _string_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(a=left, b=right).ratio()


def _candidate_score(
    card: CardPrinting,
    *,
    set_code: str,
    collector_number: str,
    rarity: str,
    lang: str,
) -> float:
    score = 0.0
    if lang and card.lang == lang:
        score += 1.0

    score += 3.0 * _string_similarity(card.set_code, set_code)
    score += 4.0 * _string_similarity(card.collector_number, collector_number)

    if rarity:
        card_rarity = (card.rarity or "")[:1].upper()
        if card_rarity == rarity:
            score += 1.0

    return score


def _sorted_candidates(
    cards: list[CardPrinting],
    *,
    set_code: str,
    collector_number: str,
    rarity: str,
    lang: str,
) -> list[CardPrinting]:
    return sorted(
        cards,
        key=lambda card: _candidate_score(
            card,
            set_code=set_code,
            collector_number=collector_number,
            rarity=rarity,
            lang=lang,
        ),
        reverse=True,
    )


def resolve_card_printing(
    session: Session,
    *,
    set_code: str | None,
    collector_number: str | None,
    name: str | None,
    rarity: str | None = None,
    lang: str = "en",
    candidate_limit: int = 5,
) -> dict[str, Any]:
    normalized_set_code = normalize_set_code(set_code)
    normalized_collector_number = normalize_collector_number(collector_number)
    normalized_name = normalize_name(name)
    normalized_rarity = normalize_name(rarity).upper()[:1]
    normalized_lang = normalize_set_code(lang) or "en"

    if normalized_set_code and normalized_collector_number:
        exact_stmt = (
            select(CardPrinting)
            .where(CardPrinting.set_code == normalized_set_code)
            .where(CardPrinting.collector_number == normalized_collector_number)
            .where(CardPrinting.lang == normalized_lang)
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

        set_number_stmt = (
            select(CardPrinting)
            .where(CardPrinting.set_code == normalized_set_code)
            .where(CardPrinting.collector_number == normalized_collector_number)
            .limit(candidate_limit)
        )
        set_number_matches = list(session.execute(set_number_stmt).scalars())
        if set_number_matches:
            return {
                "status": "fallback_match",
                "match_type": "set+number",
                "card": serialize_card_printing(set_number_matches[0]),
                "candidates": [serialize_card_printing(card) for card in set_number_matches],
            }

    if normalized_collector_number and normalized_name:
        fallback_stmt = (
            select(CardPrinting)
            .where(CardPrinting.collector_number == normalized_collector_number)
            .where(CardPrinting.lang == normalized_lang)
            .where(func.lower(CardPrinting.name).like(f"%{normalized_name.lower()}%"))
            .limit(candidate_limit)
        )
        fallback_matches = list(session.execute(fallback_stmt).scalars())
        if fallback_matches:
            ranked_matches = _sorted_candidates(
                fallback_matches,
                set_code=normalized_set_code,
                collector_number=normalized_collector_number,
                rarity=normalized_rarity,
                lang=normalized_lang,
            )
            return {
                "status": "fallback_match",
                "match_type": "number+name",
                "card": serialize_card_printing(ranked_matches[0]),
                "candidates": [serialize_card_printing(card) for card in ranked_matches],
            }

    if normalized_set_code and normalized_name:
        set_name_stmt = (
            select(CardPrinting)
            .where(CardPrinting.set_code == normalized_set_code)
            .where(func.lower(CardPrinting.name).like(f"%{normalized_name.lower()}%"))
            .limit(candidate_limit)
        )
        set_name_matches = list(session.execute(set_name_stmt).scalars())
        if set_name_matches:
            ranked_matches = _sorted_candidates(
                set_name_matches,
                set_code=normalized_set_code,
                collector_number=normalized_collector_number,
                rarity=normalized_rarity,
                lang=normalized_lang,
            )
            return {
                "status": "fallback_match",
                "match_type": "name+set",
                "card": serialize_card_printing(ranked_matches[0]),
                "candidates": [serialize_card_printing(card) for card in ranked_matches],
                "needs_review": True,
            }

    if normalized_name:
        name_only_stmt = (
            select(CardPrinting)
            .where(CardPrinting.lang == normalized_lang)
            .where(func.lower(CardPrinting.name).like(f"%{normalized_name.lower()}%"))
            .limit(candidate_limit)
        )
        name_matches = list(session.execute(name_only_stmt).scalars())
        if name_matches:
            ranked_matches = _sorted_candidates(
                name_matches,
                set_code=normalized_set_code,
                collector_number=normalized_collector_number,
                rarity=normalized_rarity,
                lang=normalized_lang,
            )
            return {
                "status": "fallback_match",
                "match_type": "name_only",
                "card": serialize_card_printing(ranked_matches[0]),
                "candidates": [serialize_card_printing(card) for card in ranked_matches],
                "needs_review": True,
            }

    return {
        "status": "unresolved",
        "match_type": "none",
        "card": None,
        "candidates": [],
    }
