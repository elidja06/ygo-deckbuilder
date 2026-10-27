"""Présence des cartes dans Master Duel (pur, sans réseau ni base)."""
from __future__ import annotations


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
