# apps/api/engine/suggest_engine.py
"""Moteur de suggestions d'optimisation.

Analyse la composition du deck et renvoie trois familles de cartes, déjà filtrées
par la banlist du format (les cartes bannies sont écartées) :
  - "staple"   : incontournables du format ;
  - "handtrap" : hand traps, classées par pertinence ;
  - "tech"     : cartes en synergie directe avec l'archétype dominant du deck ;
  - "synergie" : cartes les plus liées à l'ENSEMBLE du deck (graphe card_links).

Les pools (`staples`, `hand_traps`, `tech_cards`) sont curés à la main : cela garantit
des suggestions justes et contextualisées plutôt que génériques.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Card, CardLink, HandTrap, Staple, TechCard
from engine.mdcards import md_filter_active
from engine.synergy import score_candidates
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


def _raison_synergie(avec: list[tuple[int, float]], noms: dict[int, str]) -> str:
    """« Lié à A, B, C (+2) » : les trois cartes du deck les plus liées."""
    cites = [noms[i] for i, _ in avec[:3] if i in noms]
    reste = len(avec) - len(cites)
    texte = "Lié à " + ", ".join(cites)
    return texte + (f" (+{reste})" if reste > 0 else "")


# Score minimal pour être suggérée : écarte les liens trop faibles (ex. cartes qui ne
# font que citer un pivot comme Maxx "C", déjà atténuées par score_candidates).
MIN_SYNERGY_SCORE = 0.5


async def _synergies(
    session: AsyncSession,
    deck: set[int],
    fmt: str,
    overrides: dict[int, BanStatus],
    limite: int,
) -> list[dict]:
    """Cartes hors deck, non bannies, classées par synergie cumulée avec le deck."""
    liens = (
        await session.execute(
            select(CardLink.source_id, CardLink.target_id, CardLink.kind, CardLink.weight)
            .where(CardLink.source_id.in_(list(deck)) | CardLink.target_id.in_(list(deck)))
        )
    ).all()
    deck_rows = (
        await session.execute(select(Card.id, Card.nom_fr, Card.archetype_id).where(Card.id.in_(list(deck))))
    ).all()
    noms = {r.id: r.nom_fr for r in deck_rows}
    # Archétype de toutes les cartes liées au deck (sert à repérer les cartes « pivot »).
    concernees = {i for src, tgt, _, _ in liens for i in (src, tgt)} | deck
    archetype_of = {
        cid: aid
        for cid, aid in (
            await session.execute(
                select(Card.id, Card.archetype_id).where(Card.id.in_(list(concernees)))
            )
        ).all()
    }
    archetypes = {a for a in archetype_of.values() if a is not None}
    membres: dict[int, list[int]] = {}
    if archetypes:
        for cid, aid in (
            await session.execute(
                select(Card.id, Card.archetype_id).where(Card.archetype_id.in_(archetypes))
            )
        ).all():
            membres.setdefault(aid, []).append(cid)

    scores = score_candidates(deck, liens, archetype_of, membres)
    if not scores:
        return []
    classes = sorted(scores.items(), key=lambda kv: (-kv[1]["score"], kv[0]))[:200]
    cartes = {
        c.id: c
        for c in (
            await session.execute(select(Card).where(Card.id.in_([i for i, _ in classes])))
        ).scalars()
    }
    md_seul = await md_filter_active(session, fmt)
    out: list[dict] = []
    for pid, entry in classes:
        carte = cartes.get(pid)
        if entry["score"] < MIN_SYNERGY_SCORE:
            break  # `classes` est trié : toutes les suivantes sont encore plus faibles
        if carte is None or (md_seul and carte.md_rarity is None):
            continue
        status = effective_status(carte, fmt, overrides)
        if status == "banned":
            continue
        out.append(
            _suggestion(carte, status, "synergie", _raison_synergie(entry["avec"], noms))
        )
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

    # 0) Synergies avec l'ensemble du deck (plus d'items que les autres blocs)
    suggestions += await _synergies(session, deck, fmt, overrides, limite_par_categorie + 6)

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
