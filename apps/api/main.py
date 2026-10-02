# apps/api/main.py
"""API FastAPI du deckbuilder.

Nouveautés :
  - recherche non tronquée (limite portée à 120) et triée par pertinence
  - filtre par nature de carte (?types=spell,trap,fusion,...)
  - exclusion d'archétypes (EXCLUDED_ARCHETYPES)
  - /cards/by-archetype : toutes les cartes du même archétype ("Cartes liées")
"""
from __future__ import annotations

from collections import Counter
from typing import Literal

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import Archetype, Card, Matchup
from engine.banlist import card_to_dict, effective_status, load_overrides
from engine.combo_engine import generate_combos
from engine.suggest_engine import suggest

Format = Literal["advanced", "traditional", "speed_duel", "master_duel"]

# Archétypes masqués dans la recherche (mettre la liste à vide pour tout afficher).
EXCLUDED_ARCHETYPES: list[str] = []

# Nature de carte -> motifs de frame_type correspondants.
TYPE_FILTERS: dict[str, list[str]] = {
    "spell": ["spell"],
    "trap": ["trap"],
    "normal": ["normal"],
    "effect": ["effect"],
    "ritual": ["ritual"],
    "fusion": ["fusion"],
    "synchro": ["synchro"],
    "xyz": ["xyz"],
    "link": ["link"],
    "pendulum": ["pendulum"],
}

app = FastAPI(title="YGO Deckbuilder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DeckBody(BaseModel):
    cardIds: list[int]
    format: Format = "master_duel"


def _apply_type_filter(stmt, types: str | None):
    """Restreint aux natures de carte demandées (liste séparée par des virgules)."""
    if not types:
        return stmt
    motifs: list[str] = []
    for t in types.split(","):
        motifs += TYPE_FILTERS.get(t.strip().lower(), [])
    if not motifs:
        return stmt
    return stmt.where(or_(*[Card.frame_type.ilike(f"%{m}%") for m in motifs]))


async def _excluded_archetype_ids(session: AsyncSession) -> list[int]:
    if not EXCLUDED_ARCHETYPES:
        return []
    rows = (
        await session.execute(
            select(Archetype.id).where(Archetype.nom.in_(EXCLUDED_ARCHETYPES))
        )
    ).scalars().all()
    return list(rows)


# ------------------------------- Recherche --------------------------------- #
@app.get("/cards/search")
async def cards_search(
    q: str = Query(min_length=2),
    format: Format = "master_duel",
    types: str | None = None,
    limit: int = 120,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Recherche par nom FR. `types` filtre la nature (spell,trap,fusion,...)."""
    overrides = await load_overrides(session, format)
    exclus = await _excluded_archetype_ids(session)

    stmt = select(Card).where(Card.nom_fr.ilike(f"%{q}%"))
    if exclus:
        stmt = stmt.where(
            or_(Card.archetype_id.is_(None), Card.archetype_id.not_in(exclus))
        )
    stmt = _apply_type_filter(stmt, types)
    # Les cartes dont le nom COMMENCE par la recherche remontent en premier.
    stmt = stmt.order_by(
        Card.nom_fr.ilike(f"{q}%").desc(), Card.nom_fr
    ).limit(max(1, min(limit, 300)))

    cards = (await session.execute(stmt)).scalars().all()
    return [card_to_dict(c, effective_status(c, format, overrides)) for c in cards]


# --------------------------- Cartes liées (archétype) ----------------------- #
@app.get("/cards/by-archetype")
async def cards_by_archetype(
    card_id: int,
    format: Format = "master_duel",
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Toutes les cartes du même archétype que `card_id` (bouton « Cartes liées »)."""
    carte = await session.get(Card, card_id)
    if carte is None or carte.archetype_id is None:
        return []
    overrides = await load_overrides(session, format)
    cards = (
        await session.execute(
            select(Card)
            .where(Card.archetype_id == carte.archetype_id)
            .order_by(Card.frame_type, Card.nom_fr)
            .limit(300)
        )
    ).scalars().all()
    return [card_to_dict(c, effective_status(c, format, overrides)) for c in cards]


# -------------------------------- Combos ----------------------------------- #
@app.post("/combos/generate")
async def combos_generate(
    body: DeckBody, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    return await generate_combos(session, body.cardIds, body.format)


# ------------------------------ Suggestions -------------------------------- #
@app.post("/suggest")
async def suggest_endpoint(
    body: DeckBody, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    return await suggest(session, body.cardIds, body.format)


# -------------------------------- Matchups --------------------------------- #
@app.get("/meta/matchups")
async def meta_matchups(
    archetype_id: int, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (
        await session.execute(
            select(Matchup).where(Matchup.archetype_id == archetype_id)
        )
    ).scalars().all()
    return [
        {"deckAdverse": m.deck_adverse, "faveur": m.faveur, "conseilFr": m.conseil_fr or ""}
        for m in rows
    ]


@app.post("/meta/matchups/by-deck")
async def matchups_by_deck(
    body: DeckBody, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Matchups de l'archétype dominant du deck."""
    rows = (
        await session.execute(
            select(Card.archetype_id).where(
                Card.id.in_(set(body.cardIds)), Card.archetype_id.is_not(None)
            )
        )
    ).scalars().all()
    if not rows:
        return []
    dominant = Counter(rows).most_common(1)[0][0]
    matchups = (
        await session.execute(select(Matchup).where(Matchup.archetype_id == dominant))
    ).scalars().all()
    return [
        {"deckAdverse": m.deck_adverse, "faveur": m.faveur, "conseilFr": m.conseil_fr or ""}
        for m in matchups
    ]