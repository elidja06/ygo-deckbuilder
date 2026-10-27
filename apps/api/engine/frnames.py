# apps/api/engine/frnames.py
"""Lecture des noms français de cartes depuis l'API MediaWiki de Yugipedia.

Une page de carte contient un modèle `{{CardTable2 | fr_name = … | de_name = … }}`.
L'API renvoie jusqu'à 50 pages par requête ; on retrouve ensuite quelle page
correspond à quel titre demandé (normalisation de casse/underscores, redirections).

Module PUR (aucun accès réseau ni base) pour rester testable.
"""
from __future__ import annotations

import re

_FR_LINE = re.compile(r"^\|\s*fr_name\s*=(.*)$", re.M)
_WIKILINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_BR = re.compile(r"<br\s*/?>", re.I)


def parse_fr_name(wikitext: str | None) -> str | None:
    """Valeur du champ fr_name d'un texte wiki, ou None si absent / vide."""
    if not wikitext:
        return None
    m = _FR_LINE.search(wikitext)
    if not m:
        return None
    value = _BR.sub(" ", m.group(1))
    value = _WIKILINK.sub(r"\1", value)
    value = " ".join(value.split())
    return value or None


def resolve_batch(titles: list[str], payload: dict) -> dict[str, str | None]:
    """Associe chaque titre demandé à son nom français (None si introuvable).

    payload : réponse JSON (formatversion=2) de `action=query&prop=revisions&redirects=1`.
    """
    query = payload.get("query", {})

    alias: dict[str, str] = {}
    for key in ("normalized", "redirects"):
        for item in query.get(key, []):
            alias[item["from"]] = item["to"]

    names: dict[str, str | None] = {}
    for page in query.get("pages", []):
        if page.get("missing"):
            continue
        revisions = page.get("revisions") or []
        main = revisions[0].get("slots", {}).get("main", {}) if revisions else {}
        content = main.get("content") or main.get("*") or ""
        names[page["title"]] = parse_fr_name(content)

    result: dict[str, str | None] = {}
    for title in titles:
        current = title
        for _ in range(3):  # normalisation puis redirection(s)
            nxt = alias.get(current)
            if nxt is None or nxt == current:
                break
            current = nxt
        result[title] = names.get(current)
    return result
