# apps/api/engine/banlist.py
"""Résolution de la légalité d'une carte par format.

Principe : le statut effectif d'une carte = correction manuelle (`banlist_overrides`)
si elle existe, SINON la donnée API stockée localement (`cards.ban_tcg`), normalisée
selon le format. C'est le COALESCE(override, api, 'unlimited') du cahier des charges.

Master Duel et Speed Duel n'ont PAS de banlist exposée par l'API YGOPRODeck :
pour ces formats, la table d'overrides est la seule source de vérité (base = illimité).
"""
from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BanlistOverride, Card

BanStatus = Literal["banned", "limited", "semi_limited", "unlimited"]

# Statut API ("Banned"/"Limited"/"Semi-Limited") -> notre énum interne.
_API_STATUS_MAP: dict[str, BanStatus] = {
    "banned": "banned",
    "forbidden": "banned",
    "limited": "limited",
    "semi-limited": "semi_limited",
    "semi limited": "semi_limited",
}

# Nombre d'exemplaires autorisés par statut.
_MAX_COPIES: dict[BanStatus, int] = {
    "banned": 0,
    "limited": 1,
    "semi_limited": 2,
    "unlimited": 3,
}


def normalize_api_status(raw: str | None) -> BanStatus | None:
    """Normalise un libellé de banlist API. Renvoie None si la carte n'y figure pas."""
    if not raw:
        return None
    return _API_STATUS_MAP.get(raw.strip().lower())


def base_status(card: Card, fmt: str) -> BanStatus:
    """Statut de base issu des données API, avant application des overrides."""
    if fmt in ("master_duel", "speed_duel"):
        # Aucune donnée API fiable : on part d'illimité, les overrides feront foi.
        return "unlimited"

    tcg = card.ban_tcg  # déjà normalisé lors de la synchro (ou None)
    if fmt == "traditional":
        # Format Traditional : les cartes Forbidden passent à Limited ;
        # les listes Limited/Semi-Limited s'appliquent normalement.
        if tcg == "banned":
            return "limited"
        return tcg or "unlimited"  # type: ignore[return-value]

    # Format Advanced (par défaut) : on suit la banlist TCG telle quelle.
    return tcg or "unlimited"  # type: ignore[return-value]


def effective_status(card: Card, fmt: str, overrides: dict[int, BanStatus]) -> BanStatus:
    """Statut final : override prioritaire, sinon statut de base API."""
    return overrides.get(card.id) or base_status(card, fmt)


def max_copies(status: BanStatus) -> int:
    """Nombre d'exemplaires jouables pour un statut donné."""
    return _MAX_COPIES[status]


async def load_overrides(session: AsyncSession, fmt: str) -> dict[int, BanStatus]:
    """Charge en un seul SELECT toutes les corrections manuelles d'un format.

    Conçu pour être appelé une fois par requête, puis réutilisé sur chaque carte
    (évite un LEFT JOIN par carte). Le LEFT JOIN logique est ainsi réalisé en
    mémoire via `effective_status`.
    """
    rows = (
        await session.execute(
            select(BanlistOverride.card_id, BanlistOverride.statut).where(
                BanlistOverride.format == fmt
            )
        )
    ).all()
    return {card_id: statut for card_id, statut in rows}  # type: ignore[misc]


def card_to_dict(card: Card, status: BanStatus) -> dict:
    """Sérialise une carte au format attendu par le front (camelCase, cf. ygoApi.ts)."""
    return {
        "id": card.id,
        "nomFr": card.nom_fr,
        "type": card.type,
        "frameType": card.frame_type or "",
        "attribut": card.attribut,
        "race": card.race,
        "niveauRangLink": card.niveau_rang_link,
        "atk": card.atk,
        "def": card.def_,
        "effetFr": card.effet_fr or "",
        "imageLocale": card.image_locale or "",
        "langue": card.langue or "fr",
        "banStatus": status,
    }
