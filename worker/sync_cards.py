#!/usr/bin/env python3
# worker/sync_cards.py
"""Worker de synchronisation YGOPRODeck -> PostgreSQL + images locales.

Pipeline :
  1. checkDBVer.php : on ne resynchronise que si la version a changé (sauf --force).
  2. cardinfo.php?language=fr : un seul GET récupère tout le pool FR.
  3. Upsert des `archetypes` puis des `cards` (SQLAlchemy + ON CONFLICT).
  4. Téléchargement des images manquantes vers public/cards/{id}.jpg, en respectant
     strictement le plafond de 20 req/s de l'API (on se cale à 15 pour la marge).

Lancement :
    PYTHONPATH=apps/api python worker/sync_cards.py [--force]
(le sys.path ci-dessous rend l'import `db.*` fonctionnel sans configuration.)
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from datetime import datetime, timezone

import httpx
from aiolimiter import AsyncLimiter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Rend les modules de l'API (db.*, engine.*) importables depuis ce script externe.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from db.database import SessionLocal  # noqa: E402
from db.models import Archetype, Card, SyncState  # noqa: E402
from engine.banlist import normalize_api_status  # noqa: E402

API_BASE = "https://db.ygoprodeck.com/api/v7"
IMAGE_DIR = pathlib.Path("apps/web/public/cards")

# Plafond API = 20 req/s. On se limite à 15/s pour ne jamais frôler le bannissement.
RATE_LIMITER = AsyncLimiter(max_rate=15, time_period=1.0)
# Concurrence des téléchargements (bornée séparément du débit).
IMAGE_CONCURRENCY = 8

UPSERT_CHUNK = 500


# --------------------------------------------------------------------------- #
#  Étape 1 — Version de base                                                   #
# --------------------------------------------------------------------------- #
async def fetch_db_version(client: httpx.AsyncClient) -> str:
    resp = await client.get(f"{API_BASE}/checkDBVer.php", timeout=60.0)
    resp.raise_for_status()
    # Réponse : [{"database_version": "...", "last_update_date": "..."}]
    return str(resp.json()[0]["database_version"])


async def already_synced(version: str) -> bool:
    async with SessionLocal() as session:
        state = await session.get(SyncState, 1)
        return state is not None and state.last_db_version == version


# --------------------------------------------------------------------------- #
#  Étape 2 — Dump complet en français                                          #
# --------------------------------------------------------------------------- #
async def fetch_full_dump_fr(client: httpx.AsyncClient) -> list[dict]:
    async with RATE_LIMITER:
        resp = await client.get(
            f"{API_BASE}/cardinfo.php",
            params={"language": "fr"},
            timeout=120.0,  # le dump complet pèse plusieurs Mo
        )
    resp.raise_for_status()
    return resp.json()["data"]


def parse_card(raw: dict, archetype_id: int | None) -> dict:
    """Transforme une carte API en valeurs prêtes pour l'upsert ORM.

    Les Link n'ont pas de `level` mais un `linkval` : on unifie dans
    `niveau_rang_link`. On normalise le statut de banlist API dès l'ingestion.
    """
    niveau = raw["level"] if "level" in raw else raw.get("linkval")
    ban = raw.get("banlist_info") or {}
    card_id = int(raw["id"])
    return {
        "id": card_id,
        "archetype_id": archetype_id,
        "nom_fr": raw["name"],
        "type": raw["type"],
        "frame_type": raw.get("frameType"),
        "attribut": raw.get("attribute"),
        "race": raw.get("race"),
        "niveau_rang_link": niveau,
        "atk": raw.get("atk"),
        "def": raw.get("def"),
        "effet_fr": raw.get("desc"),
        "image_locale": f"/cards/{card_id}.jpg",
        "ban_tcg": normalize_api_status(ban.get("ban_tcg")),
        "ban_ocg": normalize_api_status(ban.get("ban_ocg")),
    }


# --------------------------------------------------------------------------- #
#  Étape 3 — Upsert en base                                                    #
# --------------------------------------------------------------------------- #
async def upsert_archetypes(cards_raw: list[dict]) -> dict[str, int]:
    """Insère les archétypes manquants et renvoie la map nom -> id."""
    noms = sorted({c["archetype"] for c in cards_raw if c.get("archetype")})
    async with SessionLocal() as session:
        if noms:
            stmt = (
                pg_insert(Archetype)
                .values([{"nom": n} for n in noms])
                .on_conflict_do_nothing(index_elements=[Archetype.nom])
            )
            await session.execute(stmt)
            await session.commit()
        rows = (await session.execute(select(Archetype.nom, Archetype.id))).all()
    return {nom: aid for nom, aid in rows}


async def upsert_cards(cards_raw: list[dict], arch_map: dict[str, int]) -> None:
    """Upsert des cartes par paquets, en écrasant les colonnes mises à jour."""
    rows = [parse_card(c, arch_map.get(c.get("archetype"))) for c in cards_raw]

    # Colonnes à rafraîchir lors d'un conflit sur la clé primaire `id`.
    updatable = [
        "archetype_id", "nom_fr", "type", "frame_type", "attribut", "race",
        "niveau_rang_link", "atk", "def", "effet_fr", "image_locale",
        "ban_tcg", "ban_ocg",
    ]

    async with SessionLocal() as session:
        for i in range(0, len(rows), UPSERT_CHUNK):
            chunk = rows[i : i + UPSERT_CHUNK]
            stmt = pg_insert(Card).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Card.id],
                set_={col: stmt.excluded[col] for col in updatable},
            )
            await session.execute(stmt)
        await session.commit()


async def mark_synced(version: str) -> None:
    async with SessionLocal() as session:
        stmt = (
            pg_insert(SyncState)
            .values(id=1, last_db_version=version, synced_at=datetime.now(timezone.utc))
            .on_conflict_do_update(
                index_elements=[SyncState.id],
                set_={
                    "last_db_version": version,
                    "synced_at": datetime.now(timezone.utc),
                },
            )
        )
        await session.execute(stmt)
        await session.commit()


# --------------------------------------------------------------------------- #
#  Étape 4 — Images (réhébergement local, rate-limité)                         #
# --------------------------------------------------------------------------- #
async def download_image(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, card_id: int, url: str
) -> None:
    dest = IMAGE_DIR / f"{card_id}.jpg"
    if dest.exists():  # incrémental : on ne retélécharge jamais une image présente
        return
    async with sem, RATE_LIMITER:  # concurrence ET débit bornés
        resp = await client.get(url, timeout=30.0)
        if resp.status_code == 200:
            dest.write_bytes(resp.content)


async def download_missing_images(
    client: httpx.AsyncClient, cards_raw: list[dict]
) -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(IMAGE_CONCURRENCY)
    tasks = []
    for c in cards_raw:
        images = c.get("card_images") or []
        if not images:
            continue
        # Première entrée = artwork par défaut, clé sur l'id de la carte.
        tasks.append(
            download_image(client, sem, int(c["id"]), images[0]["image_url"])
        )
    # gather borné par le sémaphore + le rate limiter ; tolérant aux erreurs unitaires.
    for batch_start in range(0, len(tasks), 1000):
        await asyncio.gather(
            *tasks[batch_start : batch_start + 1000], return_exceptions=True
        )


# --------------------------------------------------------------------------- #
#  Orchestration                                                               #
# --------------------------------------------------------------------------- #
async def run(force: bool = False) -> None:
    headers = {"User-Agent": "ygo-deckbuilder-sync/1.0"}
    async with httpx.AsyncClient(headers=headers) as client:
        version = await fetch_db_version(client)
        print(f"[sync] version base distante : {version}")

        if not force and await already_synced(version):
            print("[sync] déjà à jour, rien à faire.")
            return

        print("[sync] récupération du dump FR…")
        cards_raw = await fetch_full_dump_fr(client)
        print(f"[sync] {len(cards_raw)} cartes reçues.")

        arch_map = await upsert_archetypes(cards_raw)
        print(f"[sync] {len(arch_map)} archétypes en base.")

        await upsert_cards(cards_raw, arch_map)
        print("[sync] cartes upsertées.")

        print("[sync] téléchargement des images manquantes (≤15 req/s)…")
        await download_missing_images(client, cards_raw)

        await mark_synced(version)
        print("[sync] terminé.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronisation YGOPRODeck.")
    parser.add_argument(
        "--force", action="store_true", help="resynchroniser même si la version est identique"
    )
    args = parser.parse_args()
    asyncio.run(run(force=args.force))


if __name__ == "__main__":
    main()
