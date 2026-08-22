#!/usr/bin/env python3
# worker/seed_vsk9.py
"""Seed de données compétitives Vanquish Soul (VSK9) — format Master Duel.

Aucun passcode n'est codé en dur : on les résout depuis l'API YGOPRODeck
(noms anglais -> id, puis données FR par id), on upsert les `cards`
correspondantes, puis on peuple archetypes / combos / matchups / staples /
hand_traps / tech_cards. Idempotent (purge des lignes VSK9 avant réinsertion).

    PYTHONPATH=apps/api python worker/seed_vsk9.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import httpx
from aiolimiter import AsyncLimiter
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from db.database import SessionLocal  # noqa: E402
from db.models import (  # noqa: E402
    Archetype, Card, Combo, ComboStep, HandTrap, Matchup, Staple, TechCard,
)
from engine.banlist import normalize_api_status  # noqa: E402

API = "https://db.ygoprodeck.com/api/v7"
RATE = AsyncLimiter(15, 1)
ARCHETYPE = "Vanquish Soul"

# alias interne -> nom ANGLAIS exact (clé de résolution, stable et non traduit)
NEEDED: dict[str, str] = {
    # noyau VS
    "razen":      "Vanquish Soul Razen",
    "madlove":    "Vanquish Soul Dr. Mad Love",
    "caesar":     "Vanquish Soul Caesar Valius",
    "borger":     "Vanquish Soul Heavy Borger",
    "pantera":    "Vanquish Soul Pantera",
    "jiaolong":   "Vanquish Soul Jiaolong",
    "holliesue":  "Vanquish Soul Hollie Sue",
    "rock":       "Rock of the Vanquisher",
    "stake":      "Stake your Soul!",
    "start":      "Vanquish Soul, Start!",
    "snowdevil":  "Vanquish Soul Snow Devil",
    # staples / hand traps
    "maxxc":      'Maxx "C"',
    "ash":        "Ash Blossom & Joyous Spring",
    "imperm":     "Infinite Impermanence",
    "nibiru":     "Nibiru, the Primal Being",
    "ddcrow":     "D.D. Crow",
    "calledby":   "Called by the Grave",
    # tech
    "fenrir":     "Kashtira Fenrir",
    "kurikara":   "Kurikara Divincarnate",
}


# --------------------------------------------------------------------------- #
#  Résolution des IDs + données FR via l'API                                   #
# --------------------------------------------------------------------------- #
async def resolve_cards(client: httpx.AsyncClient) -> dict[str, dict]:
    """alias -> carte FR (dict API). 2 requêtes : id par nom EN, puis FR par id."""
    en_names = list(NEEDED.values())

    async with RATE:
        en = await client.get(
            f"{API}/cardinfo.php", params={"name": "|".join(en_names)}, timeout=60
        )
    en.raise_for_status()
    by_en = {c["name"].lower(): c for c in en.json().get("data", [])}

    alias_id: dict[str, int] = {}
    for alias, en_name in NEEDED.items():
        card = by_en.get(en_name.lower())
        if card:
            alias_id[alias] = int(card["id"])
        else:
            print(f"[seed] WARN  carte introuvable : {en_name!r} (alias {alias})")

    if not alias_id:
        raise RuntimeError("Aucune carte résolue — abandon.")

    ids = ",".join(str(i) for i in alias_id.values())
    async with RATE:
        fr = await client.get(
            f"{API}/cardinfo.php", params={"language": "fr", "id": ids}, timeout=60
        )
    fr.raise_for_status()
    fr_by_id = {int(c["id"]): c for c in fr.json().get("data", [])}

    return {alias: fr_by_id[cid] for alias, cid in alias_id.items() if cid in fr_by_id}


def parse_card(raw: dict, archetype_id: int | None) -> dict:
    niveau = raw["level"] if "level" in raw else raw.get("linkval")
    ban = raw.get("banlist_info") or {}
    cid = int(raw["id"])
    return {
        "id": cid, "archetype_id": archetype_id, "nom_fr": raw["name"],
        "type": raw["type"], "frame_type": raw.get("frameType"),
        "attribut": raw.get("attribute"), "race": raw.get("race"),
        "niveau_rang_link": niveau, "atk": raw.get("atk"), "def": raw.get("def"),
        "effet_fr": raw.get("desc"), "image_locale": f"/cards/{cid}.jpg",
        "ban_tcg": normalize_api_status(ban.get("ban_tcg")),
        "ban_ocg": normalize_api_status(ban.get("ban_ocg")),
    }


# --------------------------------------------------------------------------- #
#  Données métier VSK9                                                          #
# --------------------------------------------------------------------------- #
# Combos : `parent=None` => étape racine = carte requise au départ
# (le combo_engine calcule `realisable` sur l'ensemble de ces cartes racines).
COMBOS = [
    {
        "nom": "Démarrage 1 carte — Razen",
        "cartes_requises": 1,
        "resultat": "Rock of the Vanquisher en main + Razen rejoué + 1 monstre VS "
                    "recherché : protection de Rock et révélation prête pour le tour adverse.",
        "requis": ["razen"],
        "steps": [
            ("s0", None, "razen", "invocation_normale",
             "Invoquer Normalement Vanquish Soul Razen."),
            ("s1", "s0", "razen", "activation_effet",
             "Effet de Razen à l'invocation : ajouter 1 monstre « Vanquish Soul » "
             "(sauf Razen) du Deck à la main. Cherchez l'Attribut qui vous manque "
             "(TÉNÈBRES ou TERRE)."),
            ("s2", "s1", "rock", "invocation_link",
             "Invocation Lien de Rock of the Vanquisher en utilisant Razen comme matériel."),
            ("s3", "s2", "rock", "activation_effet",
             "Effet de Rock : récupérer Razen du cimetière vers la main. Vous gardez "
             "Razen en main comme coût de révélation et relance."),
        ],
    },
    {
        "nom": "Démarrage 2 cartes — Stake Your Soul! + Razen",
        "cartes_requises": 2,
        "resultat": "Corps FEU supplémentaire posé + Razen recherché + Rock : "
                    "double menace pour le grind.",
        "requis": ["razen", "stake"],
        "steps": [
            ("a", None, "razen", "invocation_normale",
             "Invoquer Normalement Razen et chercher avec son effet le monstre "
             "« Vanquish Soul » de l'Attribut manquant."),
            ("b", None, "stake", "activation_effet",
             "Activer Stake Your Soul! en révélant Razen (FEU) en main comme coût."),
            ("c", "b", "jiaolong", "invocation_speciale",
             "Invocation Spéciale d'un monstre « Vanquish Soul » FEU de nom différent "
             "(Vanquish Soul Jiaolong) depuis le Deck. Il retourne en main à la End "
             "Phase — exactement ce que VS recherche."),
            ("d", "c", "rock", "invocation_link",
             "Lien Rock of the Vanquisher avec Razen, puis récupérer un « Vanquish "
             "Soul » du cimetière pour installer la protection."),
        ],
    },
]

MATCHUPS = [
    ("Ryzeal", "defavorable",
     "Combo rapide qui pose ses Xyz tôt. Gardez Imperm/Ash pour casser l'accès "
     "(Ext Ryzeal limité, Ryzeal Cross banni en MD : leur consistance a baissé). "
     "Posez Caesar Valius + une disruption avant qu'ils ne déballent."),
    ("Tenpai Dragon", "defavorable",
     "OTK par la Battle Phase. Priorisez Snow Devil et les effets de protection/"
     "destruction pour survivre au tour ; gardez une disruption pour Tenpai Fadra. "
     "Ne surextendez pas dans Bonden."),
    ("Kashtira", "defavorable",
     "Arise-Heart bannit vos ressources et verrouille vos zones. Timez vos "
     "révélations pour stopper le combo tôt ; Dr. Mad Love (bounce non-ciblé, sans "
     "destruction) passe la protection. Ne laissez pas Riseheart libre."),
    ("Miroir VSK9", "equilibre",
     "Course au grind : la première disruption bien placée (Calamity Caesar / "
     "Dr. Mad Love) décide. Conservez vos Attributs en main pour jouer sur leur tour."),
    ("Midrange / combo lent", "favorable",
     "VS out-grind la majorité des stratégies à ressources : multipliez les "
     "disruptions sur leur tour et gagnez la partie longue."),
]

# staples du format Master Duel
STAPLES = ["maxxc", "ash", "imperm", "nibiru", "ddcrow", "calledby"]
# hand traps + priorité (pertinence décroissante)
HANDTRAPS = [("maxxc", 100), ("ash", 90), ("imperm", 85), ("nibiru", 70), ("ddcrow", 65)]
# tech cards en synergie d'archétype VSK9
TECH = [
    ("fenrir",
     "Corps TERRE révélable pour les coûts VS, briseur going-second qui bannit, "
     "et accès fiable à l'Attribut TERRE."),
    ("kurikara",
     "Monstre FEU révélable qui se défausse pour bannir un monstre adverse : "
     "fournit l'Attribut FEU et un out de plateau."),
]


# --------------------------------------------------------------------------- #
#  Insertion                                                                   #
# --------------------------------------------------------------------------- #
async def seed() -> None:
    async with httpx.AsyncClient(headers={"User-Agent": "ygo-seed/1.0"}) as client:
        cards = await resolve_cards(client)
    print(f"[seed] {len(cards)} cartes résolues.")

    async with SessionLocal() as s:
        # 1) archetypes (depuis les données API + garantie de "Vanquish Soul")
        noms = {c.get("archetype") for c in cards.values() if c.get("archetype")}
        noms.add(ARCHETYPE)
        await s.execute(
            pg_insert(Archetype)
            .values([{"nom": n} for n in sorted(noms)])
            .on_conflict_do_nothing(index_elements=[Archetype.nom])
        )
        await s.flush()
        arch_map = {
            n: i for n, i in (await s.execute(select(Archetype.nom, Archetype.id))).all()
        }
        vs_id = arch_map[ARCHETYPE]

        # 2) cards (upsert, archetype_id renseigné depuis l'API)
        rows = [parse_card(c, arch_map.get(c.get("archetype"))) for c in cards.values()]
        updatable = ["archetype_id", "nom_fr", "type", "frame_type", "attribut",
                     "race", "niveau_rang_link", "atk", "def", "effet_fr",
                     "image_locale", "ban_tcg", "ban_ocg"]
        stmt = pg_insert(Card).values(rows)
        await s.execute(stmt.on_conflict_do_update(
            index_elements=[Card.id],
            set_={c: stmt.excluded[c] for c in updatable},
        ))
        cid = {alias: int(c["id"]) for alias, c in cards.items()}  # alias -> passcode

        # 3) purge idempotente des lignes VSK9 gérées par ce seed
        await s.execute(delete(Combo).where(Combo.archetype_id == vs_id))  # cascade steps
        await s.execute(delete(Matchup).where(Matchup.archetype_id == vs_id))
        await s.execute(delete(TechCard).where(TechCard.archetype_id == vs_id))
        managed = [cid[a] for a in set(STAPLES) | {h for h, _ in HANDTRAPS} if a in cid]
        await s.execute(delete(Staple).where(
            Staple.format == "master_duel", Staple.card_id.in_(managed)))
        await s.execute(delete(HandTrap).where(HandTrap.card_id.in_(managed)))

        # 4) combos + steps
        for cb in COMBOS:
            if not all(a in cid for a in cb["requis"]):
                print(f"[seed] SKIP combo {cb['nom']!r} (carte requise non résolue)")
                continue
            combo = Combo(archetype_id=vs_id, nom=cb["nom"],
                          cartes_requises=cb["cartes_requises"], resultat=cb["resultat"])
            s.add(combo)
            await s.flush()
            local: dict[str, int] = {}
            for ordre, (key, parent, alias, action, txt) in enumerate(cb["steps"]):
                step = ComboStep(
                    combo_id=combo.id, card_id=cid.get(alias), ordre=ordre,
                    parent_step_id=local.get(parent) if parent else None,
                    action=action, explication_fr=txt,
                )
                s.add(step)
                await s.flush()
                local[key] = step.id

        # 5) matchups
        s.add_all([
            Matchup(archetype_id=vs_id, deck_adverse=adv, faveur=fav, conseil_fr=tip)
            for adv, fav, tip in MATCHUPS
        ])

        # 6) staples / hand_traps
        s.add_all([
            Staple(card_id=cid[a], format="master_duel") for a in STAPLES if a in cid
        ])
        s.add_all([
            HandTrap(card_id=cid[a], priorite=p) for a, p in HANDTRAPS if a in cid
        ])

        # 7) tech cards
        s.add_all([
            TechCard(card_id=cid[a], archetype_id=vs_id, raison=r)
            for a, r in TECH if a in cid
        ])

        await s.commit()
    print("[seed] terminé.")


if __name__ == "__main__":
    asyncio.run(seed())
