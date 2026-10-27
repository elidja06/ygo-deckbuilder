# apps/api/engine/synergy.py
"""Graphe de synergie entre cartes, déduit du texte des effets.

Principe : un effet qui CITE une autre carte (ou un thème) entre guillemets
(« Vanquish Soul », "Razen"…) indique une relation de jeu entre les deux cartes.
On transforme ces citations en arêtes pondérées :

  - kind "name"  : la citation correspond exactement au nom d'une carte (poids 1.0)
  - kind "theme" : la citation est un fragment présent dans plusieurs noms de
                   cartes, typiquement un archétype (poids 0.5)

Les arêtes sont orientées (source = carte qui cite, cible = carte citée) ; la
lecture de synergie les utilise dans les deux sens.

Ce module est PUR (aucun accès base) pour rester testable sans Docker.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# « Nom », "Nom" ou “Nom”
_QUOTED = re.compile(r'«\s*([^»]{2,80}?)\s*»|"([^"]{2,80}?)"|“([^”]{2,80}?)”')

MIN_FRAGMENT_LEN = 4      # ignore les fragments trop courts (« C », « Lv »…)
MAX_THEME_MATCHES = 80    # au-delà, le fragment est trop générique (« Dragon »…)
WEIGHT_NAME = 1.0
WEIGHT_THEME = 0.5


def normalize(text: str) -> str:
    """Minuscule, apostrophes et espaces unifiés (les accents sont conservés)."""
    t = unicodedata.normalize("NFKC", text).casefold()
    t = t.replace("’", "'").replace("`", "'")
    return " ".join(t.split())


def extract_quoted(text: str | None) -> list[str]:
    """Termes cités entre guillemets, normalisés et dédoublonnés (ordre conservé)."""
    if not text:
        return []
    seen: dict[str, None] = {}
    for m in _QUOTED.finditer(text):
        raw = next(g for g in m.groups() if g)
        seen.setdefault(normalize(raw), None)
    return list(seen)


def build_edges(cards: Iterable[dict]) -> list[dict]:
    """cards : dicts {"id", "name", "text"} -> arêtes {"source_id","target_id","kind","weight"}."""
    cards = list(cards)
    names = [(normalize(c["name"]), int(c["id"])) for c in cards]
    exact: dict[str, list[int]] = {}
    for n, cid in names:
        exact.setdefault(n, []).append(cid)

    cited = {int(c["id"]): extract_quoted(c.get("text")) for c in cards}

    # Fragments uniques -> cartes dont le nom les contient (calculé une seule fois).
    fragment_matches: dict[str, list[int]] = {}
    for frags in cited.values():
        for f in frags:
            if len(f) < MIN_FRAGMENT_LEN or f in fragment_matches:
                continue
            fragment_matches[f] = [cid for n, cid in names if f in n]

    best: dict[tuple[int, int], tuple[float, str]] = {}

    def put(src: int, dst: int, weight: float, kind: str) -> None:
        if src == dst:
            return
        key = (src, dst)
        if key not in best or weight > best[key][0]:
            best[key] = (weight, kind)

    for src, frags in cited.items():
        for f in frags:
            exact_ids = exact.get(f, [])
            for dst in exact_ids:
                put(src, dst, WEIGHT_NAME, "name")
            if len(f) < MIN_FRAGMENT_LEN:
                continue
            matches = fragment_matches.get(f, [])
            if 2 <= len(matches) <= MAX_THEME_MATCHES:
                for dst in matches:
                    if dst not in exact_ids:
                        put(src, dst, WEIGHT_THEME, "theme")

    return [
        {"source_id": s, "target_id": t, "kind": k, "weight": w}
        for (s, t), (w, k) in best.items()
    ]
