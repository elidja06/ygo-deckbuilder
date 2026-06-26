# apps/api/db/models.py
"""Modèles ORM (SQLAlchemy 2.0, style typé `Mapped`).

Reprend schema.sql à l'identique et ajoute :
  - 2 colonnes `ban_tcg` / `ban_ocg` sur `cards` (statut de banlist API stocké
    localement, base du COALESCE de banlist.py) ;
  - les tables de suggestion `staples`, `hand_traps`, `tech_cards` ;
  - `sync_state` pour le suivi de version du worker.
Voir sql/schema_additions.sql pour le DDL correspondant.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class Archetype(Base):
    __tablename__ = "archetypes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # passcode 8 chiffres
    archetype_id: Mapped[int | None] = mapped_column(ForeignKey("archetypes.id"))
    nom_fr: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    frame_type: Mapped[str | None] = mapped_column(Text)
    attribut: Mapped[str | None] = mapped_column(Text)
    race: Mapped[str | None] = mapped_column(Text)
    niveau_rang_link: Mapped[int | None] = mapped_column(SmallInteger)
    atk: Mapped[int | None] = mapped_column(Integer)
    # `def` est un mot-clé Python : on mappe l'attribut `def_` sur la colonne "def".
    def_: Mapped[int | None] = mapped_column("def", Integer)
    effet_fr: Mapped[str | None] = mapped_column(Text)
    image_locale: Mapped[str | None] = mapped_column(Text)
    # Statut de banlist API, normalisé (banned/limited/semi_limited) ou NULL.
    ban_tcg: Mapped[str | None] = mapped_column(String(16))
    ban_ocg: Mapped[str | None] = mapped_column(String(16))
    api_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nom: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False, default="master_duel")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeckCard(Base):
    __tablename__ = "deck_cards"
    __table_args__ = (UniqueConstraint("deck_id", "card_id", "zone"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deck_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    zone: Mapped[str] = mapped_column(String(8), nullable=False)  # main|extra|side
    quantite: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)


class Combo(Base):
    __tablename__ = "combos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archetype_id: Mapped[int] = mapped_column(
        ForeignKey("archetypes.id", ondelete="CASCADE"), nullable=False
    )
    nom: Mapped[str] = mapped_column(Text, nullable=False)
    cartes_requises: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    resultat: Mapped[str | None] = mapped_column(Text)

    steps: Mapped[list["ComboStep"]] = relationship(
        back_populates="combo", cascade="all, delete-orphan"
    )


class ComboStep(Base):
    __tablename__ = "combo_steps"
    __table_args__ = (UniqueConstraint("combo_id", "ordre"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    combo_id: Mapped[int] = mapped_column(
        ForeignKey("combos.id", ondelete="CASCADE"), nullable=False
    )
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id"))
    ordre: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # NULL = racine de l'arbre ; sinon = branche (alimente le flowchart React Flow).
    parent_step_id: Mapped[int | None] = mapped_column(ForeignKey("combo_steps.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    explication_fr: Mapped[str] = mapped_column(Text, nullable=False)

    combo: Mapped["Combo"] = relationship(back_populates="steps")


class Matchup(Base):
    __tablename__ = "matchups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archetype_id: Mapped[int] = mapped_column(
        ForeignKey("archetypes.id", ondelete="CASCADE"), nullable=False
    )
    deck_adverse: Mapped[str] = mapped_column(Text, nullable=False)
    faveur: Mapped[str] = mapped_column(String(16), nullable=False)  # favorable|equilibre|defavorable
    conseil_fr: Mapped[str | None] = mapped_column(Text)


class BanlistOverride(Base):
    __tablename__ = "banlist_overrides"
    __table_args__ = (UniqueConstraint("card_id", "format"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    statut: Mapped[str] = mapped_column(String(16), nullable=False)  # banned|limited|semi_limited|unlimited
    source: Mapped[str | None] = mapped_column(Text)


# ----------------- Tables de suggestion (à pré-remplir à la main) -----------------

class Staple(Base):
    """Cartes incontournables d'un format (Imperm, Cendres, etc.)."""
    __tablename__ = "staples"
    __table_args__ = (UniqueConstraint("card_id", "format"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)


class HandTrap(Base):
    """Hand traps classées par pertinence (priorite décroissante)."""
    __tablename__ = "hand_traps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), unique=True, nullable=False)
    priorite: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class TechCard(Base):
    """Tech cards taguées par synergie d'archétype, avec justification."""
    __tablename__ = "tech_cards"
    __table_args__ = (UniqueConstraint("card_id", "archetype_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    archetype_id: Mapped[int] = mapped_column(ForeignKey("archetypes.id"), nullable=False)
    raison: Mapped[str] = mapped_column(Text, nullable=False)


class SyncState(Base):
    """Suivi de la version de base YGOPRODeck déjà synchronisée."""
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # toujours = 1
    last_db_version: Mapped[str | None] = mapped_column(String(64))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
