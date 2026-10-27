#!/usr/bin/env python3
# worker/build_synergy.py
"""Construit le graphe de synergie (table card_links) à partir des effets des cartes.

Idempotent : la table est vidée puis reconstruite à chaque lancement.
À relancer après chaque synchronisation des cartes.

    PYTHONPATH=apps/api python worker/build_synergy.py
"""
from __future__ import annotations

import asyncio
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import delete, insert, select  # noqa: E402

from db.database import Base, SessionLocal, engine  # noqa: E402
from db.models import Card, CardLink  # noqa: E402
from engine.synergy import build_edges  # noqa: E402

CHUNK = 5000


async def run() -> None:
    # Crée la table card_links si elle n'existe pas (les autres sont laissées telles quelles).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Card.id, Card.nom_fr, Card.nom_en, Card.effet_fr)
            )
        ).all()
    cards = [
        {
            "id": r.id,
            "name": r.nom_fr,
            "alt_names": [r.nom_en] if r.nom_en else [],
            "text": r.effet_fr or "",
        }
        for r in rows
    ]
    print(f"[synergy] {len(cards)} cartes lues.")

    edges = build_edges(cards)
    kinds = collections.Counter(e["kind"] for e in edges)
    print(f"[synergy] {len(edges)} liens : {dict(kinds)}")

    async with SessionLocal() as session:
        await session.execute(delete(CardLink))
        for i in range(0, len(edges), CHUNK):
            await session.execute(insert(CardLink), edges[i : i + CHUNK])
        await session.commit()
    print("[synergy] terminé.")


if __name__ == "__main__":
    asyncio.run(run())
