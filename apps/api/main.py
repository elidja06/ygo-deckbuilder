# apps/api/main.py
"""Application FastAPI : expose les moteurs au front Next.js.

Endpoints (alignés sur ygoApi.ts) :
  GET  /cards/search?q=&format=        -> recherche floue de cartes
  POST /combos/generate {cardIds,format}-> combos réalisables (flowchart)
  POST /suggest {cardIds,format}        -> staples / hand traps / tech
  GET  /meta/matchups?archetype_id=     -> matchups d'un archétype
"""
from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import Card, Matchup
from engine.banlist import card_to_dict, effective_status, load_overrides
from engine.combo_engine import generate_combos
from engine.suggest_engine import suggest

Format = Literal["advanced", "traditional", "speed_duel", "master_duel"]

app = FastAPI(title="YGO Deckbuilder API")

# Le front (Next.js) tourne sur un autre port en dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------- Schémas d'entrée ---------------------------- #
class DeckBody(BaseModel):
    cardIds: list[int]
    format: Format = "master_duel"


# ------------------------------- Recherche --------------------------------- #
@app.get("/cards/search")
async def cards_search(
    q: str = Query(min_length=2),
    format: Format = "master_duel",
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Recherche floue par nom FR (ILIKE), statut de banlist déjà résolu."""
    overrides = await load_overrides(session, format)
    cards = (
        await session.execute(
            select(Card).where(Card.nom_fr.ilike(f"%{q}%")).order_by(Card.nom_fr).limit(40)
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
        {
            "deckAdverse": m.deck_adverse,
            "faveur": m.faveur,
            "conseilFr": m.conseil_fr or "",
        }
        for m in rows
    ]


# ---- Matchups déduits du deck (archétype dominant) ----
from collections import Counter as _Counter


@app.post("/meta/matchups/by-deck")
async def matchups_by_deck(
    body: DeckBody, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (await session.execute(
        select(Card.archetype_id).where(
            Card.id.in_(set(body.cardIds)), Card.archetype_id.is_not(None)
        )
    )).scalars().all()
    if not rows:
        return []
    dominant = _Counter(rows).most_common(1)[0][0]
    matchups = (await session.execute(
        select(Matchup).where(Matchup.archetype_id == dominant)
    )).scalars().all()
    return [
        {"deckAdverse": m.deck_adverse, "faveur": m.faveur, "conseilFr": m.conseil_fr or ""}
        for m in matchups
    ]
