#!/usr/bin/env python3
# worker/fetch_md_cards.py
"""Marque les cartes présentes dans Master Duel (colonne cards.md_rarity).

Source : champ `misc_info.md_rarity` du dump YGOPRODeck (`cardinfo.php?misc=yes`).
Une carte sans rareté est absente de Master Duel : elle est masquée de la recherche
en format Master Duel. Si le dump ne contient AUCUNE rareté, le script s'arrête sans
rien modifier. Idempotent ; à relancer après une synchronisation des cartes.

    PYTHONPATH=apps/api python worker/fetch_md_cards.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import pathlib
import sys

import httpx
from sqlalchemy import select, text, update

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from db.database import SessionLocal, engine  # noqa: E402
from db.models import Card  # noqa: E402
from engine.mdcards import extract_md_rarities  # noqa: E402

URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
HEADERS = {"User-Agent": "ygo-deckbuilder/1.0 (usage perso)"}
CHUNK = 2000


async def run(dry: bool) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE cards ADD COLUMN IF NOT EXISTS md_rarity VARCHAR(16)")
        )
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        resp = await client.get(URL, params={"misc": "yes"}, timeout=240.0)
        resp.raise_for_status()
        md = extract_md_rarities(resp.json()["data"])

    print(f"[md] {len(md)} cartes avec une rareté Master Duel dans le dump.")
    print(f"[md] raretés : {dict(collections.Counter(md.values()))}")
    if not md:
        print("[md] ARRÊT : aucune rareté trouvée (champ md_rarity absent ?). Base inchangée.")
        sys.exit(1)

    async with SessionLocal() as session:
        ids = set((await session.execute(select(Card.id))).scalars().all())
        rows = [{"id": i, "md_rarity": r} for i, r in md.items() if i in ids]
        print(f"[md] {len(rows)} cartes de la base sont dans Master Duel (sur {len(ids)}).")
        if dry:
            print("[md] --dry-run : rien n'est écrit.")
            return
        await session.execute(update(Card).values(md_rarity=None))
        for i in range(0, len(rows), CHUNK):
            await session.execute(update(Card), rows[i : i + CHUNK])
        await session.commit()
    print("[md] terminé.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cartes présentes dans Master Duel.")
    parser.add_argument("--dry-run", action="store_true", help="n'écrit rien en base")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    main()
