#!/usr/bin/env python3
# worker/fetch_fr_names.py
"""Noms français des cartes (source : Yugipedia) + noms anglais pour la recherche.

1. Ajoute la colonne cards.nom_en si besoin et la remplit pour TOUTES les cartes
   (dump anglais YGOPRODeck) : on peut ainsi chercher en anglais ou en français.
2. Pour les cartes sans traduction (langue = 'en'), lit le champ `fr_name` de leur
   page Yugipedia et remplace nom_fr (la carte passe en langue = 'fr').

Idempotent. À relancer après une synchronisation des cartes (sync_cards.py).
Requêtes espacées d'1 s, 50 pages par requête, avec un User-Agent explicite.

    PYTHONPATH=apps/api python worker/fetch_fr_names.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

import httpx
from sqlalchemy import select, text, update

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from db.database import SessionLocal, engine  # noqa: E402
from db.models import Card  # noqa: E402
from engine.frnames import resolve_batch  # noqa: E402

YGOPRO_EN = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
WIKI_API = "https://yugipedia.com/api.php"
HEADERS = {"User-Agent": "ygo-deckbuilder/1.0 (usage perso)"}
BATCH = 50      # pages par requête Yugipedia
PAUSE = 1.0     # secondes entre deux requêtes
CHUNK = 2000    # lignes par UPDATE groupé


async def ensure_columns() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE cards ADD COLUMN IF NOT EXISTS nom_en TEXT"))
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_cards_nom_en_trgm "
                    "ON cards USING gin (nom_en gin_trgm_ops)"
                )
            )
    except Exception as exc:  # extension pg_trgm absente : la recherche marche sans index
        print(f"[fr] index trigramme ignoré ({exc.__class__.__name__}).")


async def backfill_nom_en(client: httpx.AsyncClient, dry: bool) -> None:
    resp = await client.get(YGOPRO_EN, timeout=180.0)
    resp.raise_for_status()
    names = {int(c["id"]): c["name"] for c in resp.json()["data"]}
    async with SessionLocal() as session:
        ids = (await session.execute(select(Card.id))).scalars().all()
        rows = [{"id": i, "nom_en": names[i]} for i in ids if i in names]
        print(f"[fr] noms anglais : {len(rows)} cartes sur {len(ids)}.")
        if dry:
            return
        for i in range(0, len(rows), CHUNK):
            await session.execute(update(Card), rows[i : i + CHUNK])
        await session.commit()


async def fetch_wiki_batch(client: httpx.AsyncClient, titles: list[str]) -> dict:
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "redirects": 1,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
        "formatversion": 2,
        "utf8": 1,
    }
    resp = None
    for attempt in range(4):
        resp = await client.get(WIKI_API, params=params, timeout=60.0)
        if resp.status_code in (429, 500, 502, 503):
            await asyncio.sleep(3 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    assert resp is not None
    resp.raise_for_status()
    return resp.json()


async def fill_fr_names(client: httpx.AsyncClient, dry: bool, limit: int | None) -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Card.id, Card.nom_fr, Card.nom_en)
                .where(Card.langue == "en")
                .order_by(Card.id)
            )
        ).all()
    cands = [(r.id, r.nom_en or r.nom_fr) for r in rows]
    cands = [(i, t) for i, t in cands if t and "|" not in t]
    if limit:
        cands = cands[:limit]
    print(f"[fr] {len(cands)} cartes sans nom français à chercher sur Yugipedia.")

    found: list[dict] = []
    missing: list[str] = []
    for start in range(0, len(cands), BATCH):
        chunk = cands[start : start + BATCH]
        titles = [t for _, t in chunk]
        resolved = resolve_batch(titles, await fetch_wiki_batch(client, titles))
        for cid, title in chunk:
            fr = resolved.get(title)
            if fr:
                found.append({"id": cid, "nom_fr": fr, "langue": "fr", "nom_en": title})
            else:
                missing.append(title)
        done = min(start + BATCH, len(cands))
        if (start // BATCH) % 5 == 0 or done == len(cands):
            print(f"[fr] {done}/{len(cands)} traitées — {len(found)} trouvées.")
        await asyncio.sleep(PAUSE)

    print(f"[fr] trouvées : {len(found)} — sans nom français officiel : {len(missing)}")
    for row in found[:10]:
        print(f"      {row['nom_en']}  ->  {row['nom_fr']}")
    if missing:
        print("[fr] sans nom FR (premiers) :", "; ".join(missing[:25]))
    if dry:
        print("[fr] --dry-run : rien n'est écrit.")
        return

    async with SessionLocal() as session:
        for i in range(0, len(found), CHUNK):
            await session.execute(update(Card), found[i : i + CHUNK])
        await session.commit()
    print("[fr] noms français enregistrés.")


async def run(dry: bool, limit: int | None) -> None:
    await ensure_columns()
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        await backfill_nom_en(client, dry)
        await fill_fr_names(client, dry, limit)
    print("[fr] terminé.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Noms français (Yugipedia) + noms anglais.")
    parser.add_argument("--dry-run", action="store_true", help="n'écrit rien en base")
    parser.add_argument("--limit", type=int, help="ne traiter que N cartes (test)")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run, args.limit))


if __name__ == "__main__":
    main()
