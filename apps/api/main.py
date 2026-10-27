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
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import Archetype, Card, CardLink, Matchup
from engine.banlist import card_to_dict, effective_status, load_overrides
from engine.combo_engine import generate_combos
from engine.suggest_engine import suggest
from engine.synergy import describe_partner, score_partners

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


async def _md_only(session: AsyncSession, format: str) -> bool:
    """Vrai si l'on doit masquer les cartes absentes de Master Duel.

    Actif seulement en format Master Duel ET si worker/fetch_md_cards.py a déjà
    renseigné la base (sinon toute la base serait masquée).
    """
    if format != "master_duel":
        return False
    row = await session.execute(
        select(Card.id).where(Card.md_rarity.is_not(None)).limit(1)
    )
    return row.first() is not None


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
    """Recherche par nom FR ou EN. `types` filtre la nature (spell,trap,fusion,...)."""
    overrides = await load_overrides(session, format)
    exclus = await _excluded_archetype_ids(session)

    stmt = select(Card).where(
        or_(Card.nom_fr.ilike(f"%{q}%"), Card.nom_en.ilike(f"%{q}%"))
    )
    if exclus:
        stmt = stmt.where(
            or_(Card.archetype_id.is_(None), Card.archetype_id.not_in(exclus))
        )
    if await _md_only(session, format):
        stmt = stmt.where(Card.md_rarity.is_not(None))
    stmt = _apply_type_filter(stmt, types)
    # Les cartes dont le nom COMMENCE par la recherche remontent en premier.
    stmt = stmt.order_by(
        or_(
            Card.nom_fr.ilike(f"{q}%"),
            func.coalesce(Card.nom_en, "").ilike(f"{q}%"),
        ).desc(),
        Card.nom_fr,
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
    stmt = select(Card).where(Card.archetype_id == carte.archetype_id)
    if await _md_only(session, format):
        stmt = stmt.where(Card.md_rarity.is_not(None))
    cards = (
        await session.execute(stmt.order_by(Card.frame_type, Card.nom_fr).limit(300))
    ).scalars().all()
    return [card_to_dict(c, effective_status(c, format, overrides)) for c in cards]


# ------------------------- Synergies (graphe de cartes) --------------------- #
@app.get("/cards/synergies")
async def card_synergies(
    card_id: int,
    format: Format = "master_duel",
    limit: int = 40,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Cartes qui travaillent avec `card_id` (citées par son effet, ou la citant).

    Ordre des scores : nom cité (1.0, +0.25 si mutuel) > thème mutuel (0.75) >
    même archétype (0.6) > simple citation de thème (0.5) ; un lien textuel cumulé
    avec le même archétype gagne +0.1. Voir engine/synergy.py (score_partners).
    Le graphe est construit par worker/build_synergy.py.
    """
    sortants = (
        await session.execute(
            select(CardLink.target_id, CardLink.kind, CardLink.weight).where(
                CardLink.source_id == card_id
            )
        )
    ).all()
    entrants = (
        await session.execute(
            select(CardLink.source_id, CardLink.kind, CardLink.weight).where(
                CardLink.target_id == card_id
            )
        )
    ).all()

    carte_source = await session.get(Card, card_id)
    meme_archetype: list[int] = []
    if carte_source is not None and carte_source.archetype_id is not None:
        meme_archetype = list(
            (
                await session.execute(
                    select(Card.id)
                    .where(
                        Card.archetype_id == carte_source.archetype_id,
                        Card.id != card_id,
                    )
                    .limit(300)
                )
            ).scalars()
        )

    partenaires = score_partners(sortants, entrants, meme_archetype)
    if partenaires and await _md_only(session, format):
        presents = set(
            (
                await session.execute(
                    select(Card.id).where(
                        Card.id.in_(list(partenaires)), Card.md_rarity.is_not(None)
                    )
                )
            ).scalars()
        )
        partenaires = {i: p for i, p in partenaires.items() if i in presents}

    top = sorted(partenaires.items(), key=lambda kv: (-kv[1]["score"], kv[0]))
    top = top[: max(1, min(limit, 100))]
    if not top:
        return []

    cartes = {
        c.id: c
        for c in (
            await session.execute(select(Card).where(Card.id.in_([i for i, _ in top])))
        ).scalars()
    }
    overrides = await load_overrides(session, format)
    resultat: list[dict] = []
    for pid, p in top:
        carte = cartes.get(pid)
        if carte is None:
            continue
        d = card_to_dict(carte, effective_status(carte, format, overrides))
        d["synergie"] = describe_partner(p)
        resultat.append(d)
    return resultat


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