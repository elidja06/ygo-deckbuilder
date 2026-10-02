#!/usr/bin/env python3
# worker/sync_cards.py
"""Synchronisation YGOPRODeck -> PostgreSQL + images locales.

Mode HYBRIDE :
  1. dump FR  -> noms et effets en français pour tout ce qui est traduit
  2. dump EN  -> complète les cartes absentes du FR (archétypes récents :
     Vanquish Soul, Ryzeal, etc.), marquées langue='en'
  3. images téléchargées localement en respectant 15 req/s (plafond API : 20)

Lancement depuis la racine du projet :
    DATABASE_URL="postgresql+asyncpg://ygo:ygo@localhost:5432/ygo" \
    PYTHONPATH=apps/api python worker/sync_cards.py [--force]
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from db.database import SessionLocal  # noqa: E402
from db.models import Archetype, Card, SyncState  # noqa: E402
from engine.banlist import normalize_api_status  # noqa: E402

API_BASE = "https://db.ygoprodeck.com/api/v7"
IMAGE_DIR = pathlib.Path("apps/web/public/cards")

RATE_LIMITER = AsyncLimiter(max_rate=15, time_period=1.0)
IMAGE_CONCURRENCY = 8
UPSERT_CHUNK = 500


# --------------------------------------------------------------------------- #
#  Étape 1 — Version de base                                                   #
# --------------------------------------------------------------------------- #
async def fetch_db_version(client: httpx.AsyncClient) -> str:
    resp = await client.get(f"{API_BASE}/checkDBVer.php", timeout=60.0)
    resp.raise_for_status()
    return str(resp.json()[0]["database_version"])


async def already_synced(version: str) -> bool:
    async with SessionLocal() as session:
        state = await session.get(SyncState, 1)
        return state is not None and state.last_db_version == version


# --------------------------------------------------------------------------- #
#  Étape 2 — Dumps FR puis EN                                                  #
# --------------------------------------------------------------------------- #
async def fetch_dump(client: httpx.AsyncClient, language: str | None) -> list[dict]:
    params = {"language": language} if language else {}
    async with RATE_LIMITER:
        resp = await client.get(f"{API_BASE}/cardinfo.php", params=params, timeout=180.0)
    resp.raise_for_status()
    return resp.json()["data"]


def merge_dumps(fr: list[dict], en: list[dict]) -> list[dict]:
    """Garde toutes les cartes FR, complète avec les EN absentes du FR."""
    fusion: dict[int, dict] = {}
    for c in fr:
        c["_langue"] = "fr"
        fusion[int(c["id"])] = c
    ajouts = 0
    for c in en:
        cid = int(c["id"])
        if cid not in fusion:
            c["_langue"] = "en"
            fusion[cid] = c
            ajouts += 1
    print(f"[sync] {len(fr)} cartes FR + {ajouts} cartes EN complémentaires")
    return list(fusion.values())


def parse_card(raw: dict, archetype_id: int | None) -> dict:
    """Carte API -> valeurs prêtes pour l'upsert.

    Les monstres Lien n'ont pas de `level` mais un `linkval` : unifiés dans
    `niveau_rang_link`. Le statut de banlist API est normalisé à l'ingestion.
    """
    niveau = raw["level"] if "level" in raw else raw.get("linkval")
    ban = raw.get("banlist_info") or {}
    cid = int(raw["id"])
    return {
        "id": cid,
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
        "image_locale": f"/cards/{cid}.jpg",
        "langue": raw.get("_langue", "fr"),
        "ban_tcg": normalize_api_status(ban.get("ban_tcg")),
        "ban_ocg": normalize_api_status(ban.get("ban_ocg")),
    }


# --------------------------------------------------------------------------- #
#  Étape 3 — Upsert en base                                                    #
# --------------------------------------------------------------------------- #
async def upsert_archetypes(cards_raw: list[dict]) -> dict[str, int]:
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
    rows = [parse_card(c, arch_map.get(c.get("archetype"))) for c in cards_raw]
    updatable = [
        "archetype_id", "nom_fr", "type", "frame_type", "attribut", "race",
        "niveau_rang_link", "atk", "def", "effet_fr", "image_locale",
        "langue", "ban_tcg", "ban_ocg",
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
        maintenant = datetime.now(timezone.utc)
        stmt = (
            pg_insert(SyncState)
            .values(id=1, last_db_version=version, synced_at=maintenant)
            .on_conflict_do_update(
                index_elements=[SyncState.id],
                set_={"last_db_version": version, "synced_at": maintenant},
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
    if dest.exists():  # incrémental : jamais retéléchargée
        return
    async with sem, RATE_LIMITER:
        resp = await client.get(url, timeout=30.0)
        if resp.status_code == 200:
            dest.write_bytes(resp.content)


async def download_missing_images(client: httpx.AsyncClient, cards_raw: list[dict]) -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(IMAGE_CONCURRENCY)
    tasks = []
    for c in cards_raw:
        images = c.get("card_images") or []
        if images:
            tasks.append(download_image(client, sem, int(c["id"]), images[0]["image_url"]))
    for debut in range(0, len(tasks), 1000):
        await asyncio.gather(*tasks[debut : debut + 1000], return_exceptions=True)


# --------------------------------------------------------------------------- #
#  Orchestration                                                               #
# --------------------------------------------------------------------------- #
async def run(force: bool = False) -> None:
    headers = {"User-Agent": "ygo-deckbuilder-sync/2.0"}
    async with httpx.AsyncClient(headers=headers) as client:
        version = await fetch_db_version(client)
        print(f"[sync] version base distante : {version}")

        if not force and await already_synced(version):
            print("[sync] déjà à jour, rien à faire.")
            return

        print("[sync] récupération du dump FR…")
        fr = await fetch_dump(client, "fr")
        print("[sync] récupération du dump EN (complément)…")
        en = await fetch_dump(client, None)

        cards_raw = merge_dumps(fr, en)
        print(f"[sync] {len(cards_raw)} cartes au total.")

        arch_map = await upsert_archetypes(cards_raw)
        print(f"[sync] {len(arch_map)} archétypes en base.")

        await upsert_cards(cards_raw, arch_map)
        print("[sync] cartes upsertées.")

        print("[sync] téléchargement des images manquantes (≤15 req/s)…")
        await download_missing_images(client, cards_raw)

        await mark_synced(version)
        print("[sync] terminé.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronisation YGOPRODeck (hybride FR+EN).")
    parser.add_argument("--force", action="store_true", help="resynchroniser malgré la version")
    args = parser.parse_args()
    asyncio.run(run(force=args.force))


if __name__ == "__main__":
    main()