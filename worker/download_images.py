#!/usr/bin/env python3
# worker/download_images.py
"""Télécharge les images de cartes manquantes dans apps/web/public/cards/{id}.jpg.

- Reprise possible : les images déjà présentes ne sont jamais retéléchargées ;
  on peut interrompre (Ctrl+C) et relancer.
- Petite taille par défaut (~12 Ko / carte, ~200 Mo pour toute la base) ;
  `--size full` pour les grandes images (~100 Ko / carte, plus d'1 Go).
- 15 requêtes/s maximum, 8 en parallèle, avec reprise sur erreur temporaire.
- Garde-fou disque : s'arrête proprement s'il reste moins de --min-free-mb.

    PYTHONPATH=apps/api python worker/download_images.py [--size small|full] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import shutil
import sys

import httpx
from aiolimiter import AsyncLimiter
from sqlalchemy import select

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from db.database import SessionLocal  # noqa: E402
from db.models import Card  # noqa: E402

IMAGE_DIR = pathlib.Path("apps/web/public/cards")
BASE = "https://images.ygoprodeck.com/images"
HEADERS = {"User-Agent": "ygo-deckbuilder/1.0 (usage perso)"}
RATE = AsyncLimiter(max_rate=15, time_period=1.0)
CONCURRENCY = 8
GROUP = 500
RETRY_STATUS = (429, 500, 502, 503, 504)


def image_url(card_id: int, size: str) -> str:
    folder = "cards_small" if size == "small" else "cards"
    return f"{BASE}/{folder}/{card_id}.jpg"


async def fetch_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    card_id: int,
    size: str,
    stats: dict[str, int],
) -> None:
    dest = IMAGE_DIR / f"{card_id}.jpg"
    async with sem, RATE:
        for attempt in range(3):
            try:
                resp = await client.get(image_url(card_id, size), timeout=30.0)
            except httpx.HTTPError:
                await asyncio.sleep(1 + attempt)
                continue
            if resp.status_code == 200 and resp.content:
                tmp = dest.with_suffix(".part")
                tmp.write_bytes(resp.content)
                tmp.replace(dest)  # écriture atomique : jamais d'image tronquée
                stats["ok"] += 1
                return
            if resp.status_code == 404:
                stats["absentes"] += 1
                return
            if resp.status_code in RETRY_STATUS:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            break
        stats["erreurs"] += 1


async def run(size: str, limit: int | None, min_free_mb: int) -> dict[str, int]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    async with SessionLocal() as session:
        ids = (await session.execute(select(Card.id).order_by(Card.id))).scalars().all()
    missing = [i for i in ids if not (IMAGE_DIR / f"{i}.jpg").exists()]
    if limit:
        missing = missing[:limit]
    print(f"[img] {len(ids)} cartes, {len(missing)} images à télécharger ({size}).")

    stats = {"ok": 0, "absentes": 0, "erreurs": 0}
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for start in range(0, len(missing), GROUP):
            free_mb = shutil.disk_usage(IMAGE_DIR).free // (1024 * 1024)
            if free_mb < min_free_mb:
                print(
                    f"[img] ARRÊT : il ne reste que {free_mb} Mo libres "
                    f"(minimum {min_free_mb} Mo). Libérez de la place puis relancez."
                )
                break
            group = missing[start : start + GROUP]
            await asyncio.gather(*(fetch_one(client, sem, i, size, stats) for i in group))
            print(
                f"[img] {min(start + GROUP, len(missing))}/{len(missing)} — "
                f"ok {stats['ok']}, absentes {stats['absentes']}, erreurs {stats['erreurs']}"
            )
    print(f"[img] terminé : {stats}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Téléchargement des images de cartes.")
    parser.add_argument("--size", choices=("small", "full"), default="small")
    parser.add_argument("--limit", type=int, help="ne traiter que N images (test)")
    parser.add_argument("--min-free-mb", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(run(args.size, args.limit, args.min_free_mb))


if __name__ == "__main__":
    main()
