# apps/api/engine/combo_engine.py
"""Moteur de combos.

Entrée : la liste des IDs de cartes du Main Deck de l'utilisateur.
Sortie : les combos des archétypes présents, avec un drapeau `realisable` et leurs
étapes à plat (chaque étape porte son `parentId`), prêtes pour le flowchart React Flow.

Stratégie : on NE génère PAS les combos à la volée de façon combinatoire (coûteux et
peu fiable). On stocke des combos curés en base (`combos` + `combo_steps`) et on filtre
ceux dont toutes les cartes de départ (étapes racines) sont présentes dans le deck.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Card, Combo, ComboStep


async def _archetypes_in_deck(session: AsyncSession, deck: set[int]) -> set[int]:
    """IDs d'archétypes représentés par au moins une carte du deck."""
    rows = (
        await session.execute(
            select(Card.archetype_id).where(
                Card.id.in_(deck), Card.archetype_id.is_not(None)
            )
        )
    ).scalars().all()
    return set(rows)


def _serialize_step(step: ComboStep) -> dict:
    """Étape -> nœud à plat consommé par ComboFlowchart.layout() côté front."""
    return {
        "id": str(step.id),
        "parentId": str(step.parent_step_id) if step.parent_step_id else None,
        "cardId": step.card_id,
        "action": step.action,
        "explicationFr": step.explication_fr,
    }


async def generate_combos(
    session: AsyncSession, card_ids: list[int], fmt: str
) -> list[dict]:
    """Renvoie les combos pertinents pour le deck, réalisables en tête.

    `fmt` n'influence pas la logique de combo (les combos sont liés à l'archétype),
    mais reste dans la signature pour cohérence avec les autres moteurs et un éventuel
    filtrage futur (ex. exclure un combo dont une pièce est bannie dans le format).
    """
    deck = set(card_ids)
    if not deck:
        return []

    archetype_ids = await _archetypes_in_deck(session, deck)
    if not archetype_ids:
        return []

    combos = (
        await session.execute(
            select(Combo).where(Combo.archetype_id.in_(archetype_ids))
        )
    ).scalars().all()
    if not combos:
        return []

    # Chargement groupé de toutes les étapes (un seul SELECT), ordonnées.
    combo_ids = [c.id for c in combos]
    steps = (
        await session.execute(
            select(ComboStep)
            .where(ComboStep.combo_id.in_(combo_ids))
            .order_by(ComboStep.combo_id, ComboStep.ordre)
        )
    ).scalars().all()

    steps_by_combo: dict[int, list[ComboStep]] = defaultdict(list)
    for s in steps:
        steps_by_combo[s.combo_id].append(s)

    result: list[dict] = []
    for combo in combos:
        combo_steps = steps_by_combo.get(combo.id, [])

        # Cartes "de départ" = étapes racines (parent NULL) portant une carte.
        # Un combo est réalisable si toutes ces pièces sont dans le deck.
        starter_cards = {
            s.card_id
            for s in combo_steps
            if s.parent_step_id is None and s.card_id is not None
        }
        realisable = bool(starter_cards) and starter_cards.issubset(deck)

        result.append(
            {
                "id": combo.id,
                "nom": combo.nom,
                "cartesRequises": combo.cartes_requises,
                "resultat": combo.resultat or "",
                "realisable": realisable,
                "steps": [_serialize_step(s) for s in combo_steps],
            }
        )

    # Réalisables d'abord, puis du plus économique (1 carte) au plus exigeant.
    result.sort(key=lambda c: (not c["realisable"], c["cartesRequises"]))
    return result
