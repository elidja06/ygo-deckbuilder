# apps/api/engine/suggest_engine.py
"""Moteur de suggestions d'optimisation.

Analyse la composition du deck et renvoie trois familles de cartes, déjà filtrées
par la banlist du format (les cartes bannies sont écartées) :
  - "staple"   : incontournables du format ;
  - "handtrap" : hand traps, classées par pertinence ;
  - "tech"     : cartes en synergie directe avec l'archétype dominant du deck.

Les pools (`staples`, `hand_traps`, `tech_cards`) sont curés à la main : cela garantit
des suggestions justes et contextualisées plutôt que génériques.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Card, HandTrap, Staple, TechCard
from engine.banlist import (
    BanStatus,
    card_to_dict,
    effective_status,
    load_overrides,
)


async def _dominant_archetype(session: AsyncSession, deck: set[int]) -> int | None:
    """Archétype le plus représenté dans le deck (None si deck générique)."""
    rows = (
        await session.execute(
            select(Card.archetype_id).where(
                Card.id.in_(deck), Card.archetype_id.is_not(None)
            )
        )
    ).scalars().all()
    if not rows:
        return None
    return Counter(rows).most_common(1)[0][0]


def _suggestion(card: Card, status: BanStatus, categorie: str, raison: str) -> dict:
    """Construit un objet Suggestion conforme à ygoApi.ts."""
    return {"card": card_to_dict(card, status), "categorie": categorie, "raison": raison}


def _retenir(
    cards: list[Card],
    deck: set[int],
    fmt: str,
    overrides: dict[int, BanStatus],
    categorie: str,
    raison_fn,
    limite: int,
) -> list[dict]:
    """Filtre (hors deck, non banni) puis plafonne une liste de candidats."""
    out: list[dict] = []
    for card in cards:
        if card.id in deck:
            continue
        status = effective_status(card, fmt, overrides)
        if status == "banned":
            continue
        out.append(_suggestion(card, status, categorie, raison_fn(card)))
        if len(out) >= limite:
            break
    return out


async def suggest(
    session: AsyncSession, card_ids: list[int], fmt: str, limite_par_categorie: int = 6
) -> list[dict]:
    """Renvoie les suggestions d'optimisation pour le deck courant."""
    deck = set(card_ids)
    if not deck:
        return []

    overrides = await load_overrides(session, fmt)
    dominant = await _dominant_archetype(session, deck)

    suggestions: list[dict] = []

    # 1) Staples du format -------------------------------------------------
    staple_cards = (
        await session.execute(
            select(Card).join(Staple, Staple.card_id == Card.id).where(Staple.format == fmt)
        )
    ).scalars().all()
    suggestions += _retenir(
        staple_cards, deck, fmt, overrides,
        "staple", lambda c: "Staple incontournable du format.",
        limite_par_categorie,
    )

    # 2) Hand traps, par pertinence décroissante ---------------------------
    handtrap_cards = (
        await session.execute(
            select(Card)
            .join(HandTrap, HandTrap.card_id == Card.id)
            .order_by(HandTrap.priorite.desc())
        )
    ).scalars().all()
    suggestions += _retenir(
        handtrap_cards, deck, fmt, overrides,
        "handtrap", lambda c: "Hand trap pour perturber l'adversaire.",
        limite_par_categorie,
    )

    # 3) Tech cards en synergie avec l'archétype dominant ------------------
    if dominant is not None:
        tech_rows = (
            await session.execute(
                select(Card, TechCard.raison)
                .join(TechCard, TechCard.card_id == Card.id)
                .where(TechCard.archetype_id == dominant)
            )
        ).all()
        # On garde la raison curée propre à chaque tech card.
        raisons = {card.id: raison for card, raison in tech_rows}
        tech_cards = [card for card, _ in tech_rows]
        suggestions += _retenir(
            tech_cards, deck, fmt, overrides,
            "tech", lambda c: raisons.get(c.id, "Synergie d'archétype."),
            limite_par_categorie,
        )

    return suggestions
