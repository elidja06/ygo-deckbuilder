"""Présence des cartes dans Master Duel (pur, sans réseau ni base)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Card


def extract_md_rarities(data: list[dict]) -> dict[int, str]:
    """{id carte: rareté Master Duel} à partir du dump YGOPRODeck `cardinfo.php?misc=yes`.

    Les cartes sans `md_rarity` (absentes de Master Duel) sont omises.
    """
    out: dict[int, str] = {}
    for card in data:
        for info in card.get("misc_info") or []:
            rarity = info.get("md_rarity")
            if rarity:
                out[int(card["id"])] = str(rarity)
                break
    return out


async def md_filter_active(session: AsyncSession, format: str) -> bool:
    """Vrai s'il faut masquer les cartes absentes de Master Duel.

    Actif seulement en format Master Duel ET si worker/fetch_md_cards.py a déjà
    renseigné la base (sinon toute la base serait masquée).
    """
    if format != "master_duel":
        return False
    row = await session.execute(select(Card.id).where(Card.md_rarity.is_not(None)).limit(1))
    return row.first() is not None
