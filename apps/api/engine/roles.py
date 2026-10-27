# apps/api/engine/roles.py
"""Rôles des cartes (starter, extender, hand trap…) déduits du texte de l'effet.

Analyse par règles, sans IA : le texte est normalisé (minuscules, sans accents) puis
comparé à des motifs en français ET en anglais (les cartes récentes n'ont pas encore de
texte français). C'est une aide à la lecture, pas une vérité : une carte peut avoir
plusieurs rôles, et certaines subtilités de jeu échappent aux motifs.

Module PUR (aucun accès base) pour rester testable sans Docker.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

EXTRA_FRAMES = {"fusion", "synchro", "xyz", "link"}

ROLE_LABELS: dict[str, str] = {
    "starter": "Starters",
    "extender": "Extenders",
    "handtrap": "Hand traps",
    "interruption": "Interruptions",
    "removal": "Removal",
    "boardbreaker": "Board breakers",
    "draw": "Pioche",
    "brick": "Briques potentielles",
    "autre": "Autres",
}
ROLE_ORDER = list(ROLE_LABELS)


def _norm(text: str | None) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    t = t.replace("’", "'").replace("“", '"').replace("”", '"')
    return " ".join(t.split())


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.DOTALL)


# Ajouter une carte du Deck à la main
_SEARCH = _rx(
    r"\b(add|ajoute\w*)\b.{0,160}?\b(from your deck|de votre deck)\b.{0,60}?"
    r"\b(to your hand|a votre main)\b"
)
# Invoquer Spécialement une carte DEPUIS LE DECK
_SS_FROM_DECK = _rx(
    r"\b(special summon|invoque\w* .{0,30}invocation speciale|invocation speciale)\b"
    r".{0,160}?\b(from your deck|de votre deck)\b"
)
# S'invoquer soi-même / depuis cimetière, main ou bannissement
_SELF_SS = _rx(
    r"(special summon this card|special summon it\b|cette carte par invocation speciale|"
    r"invocation speciale de cette carte|invoquer cette carte)"
)
_SS_RECUP = _rx(
    r"\b(special summon|invocation speciale)\b.{0,160}?"
    r"\b(from your (gy|graveyard|banished)|de votre (cimetiere|zone de bannissement)|"
    r"banished|banni)\b"
)
# Effet qui se joue depuis la main (hand trap)
_DISCARD_SELF = _rx(
    r"(discard this card|send this card from your hand|reveal this card in your hand|"
    r"defausser cette carte|defaussez cette carte|envoyer cette carte de votre main|"
    r"envoyez cette carte de votre main)"
)
_QUICK = _rx(r"(quick effect|effet rapide|during either player's turn|tour de l'un ou l'autre)")
_NEGATE = _rx(r"\b(negate|annul\w+|neutralis\w+)\b")
_REMOVAL = _rx(
    r"\b(destroy|banish|return|send|detruire|detruisez|bannir|bannissez|renvoy\w+|envoy\w+)\b"
    r"[^.;]{0,90}\b(your opponent controls|opponent controls|controle\w* par votre adversaire|"
    r"votre adversaire controle)\b"
)
_BOARD_WIPE = _rx(
    r"\b(destroy|banish|return|detruire|detruisez|bannir|bannissez|renvoy\w+)\s+"
    r"(all|tous|toutes)\b"
)
_DRAW = _rx(r"\b(draw (\d+|1) cards?|draw \d|pioche\w* (\d+|une|1) carte)")
_NO_NORMAL = _rx(
    r"(cannot be normal summoned|cannot be normal summoned/set|"
    r"ne peut pas etre invoque\w* par invocation normale)"
)
_CONDITIONAL_SS = _rx(r"(must first be special summoned|doit d'abord etre invoque\w* par invocation speciale)")


def is_extra(frame_type: str | None) -> bool:
    return (frame_type or "").casefold() in EXTRA_FRAMES


def classify(card: dict) -> list[str]:
    """Rôles d'une carte : liste (ordre de ROLE_ORDER), jamais vide.

    card : {"frame_type", "type", "niveau", "texte"}
    """
    t = _norm(card.get("texte"))
    frame = (card.get("frame_type") or "").casefold()
    is_monster = frame not in {"spell", "trap"}
    roles: set[str] = set()

    if _SEARCH.search(t) or _SS_FROM_DECK.search(t):
        roles.add("starter")
    if _SELF_SS.search(t) or _SS_RECUP.search(t):
        roles.add("extender")
    if _DISCARD_SELF.search(t) and (_QUICK.search(t) or _NEGATE.search(t) or _REMOVAL.search(t)
                                    or _DRAW.search(t)):
        roles.add("handtrap")
    if _NEGATE.search(t):
        roles.add("interruption")
    if _REMOVAL.search(t) and not is_extra(frame):
        roles.add("removal")
    if _BOARD_WIPE.search(t):
        roles.add("boardbreaker")
    if _DRAW.search(t):
        roles.add("draw")

    # Briques potentielles : monstres du Main Deck qui ne se posent pas facilement
    if is_monster and not is_extra(frame) and "extender" not in roles:
        niveau = card.get("niveau") or 0
        if _CONDITIONAL_SS.search(t) or (_NO_NORMAL.search(t) and "starter" not in roles):
            roles.add("brick")
        elif niveau >= 7 and "starter" not in roles and "handtrap" not in roles:
            roles.add("brick")

    if not roles:
        roles.add("autre")
    return [r for r in ROLE_ORDER if r in roles]


def analyze_deck(cards: Iterable[dict]) -> dict:
    """Résumé d'un Main Deck.

    cards : une entrée PAR EXEMPLAIRE (les doublons comptent), chaque entrée de la
    forme {"id", "nom", "frame_type", "niveau", "texte"}.
    Retourne {"total", "roles": [{role, label, copies, cartes:[{id, nom, copies}]}],
    "alertes": [{niveau, message}]}.
    """
    parCarte: dict[int, dict] = {}
    for c in cards:
        e = parCarte.setdefault(c["id"], {"card": c, "copies": 0})
        e["copies"] += 1
    total = sum(e["copies"] for e in parCarte.values())

    blocs: dict[str, dict] = {}
    for e in parCarte.values():
        for role in classify(e["card"]):
            b = blocs.setdefault(role, {"copies": 0, "cartes": []})
            b["copies"] += e["copies"]
            b["cartes"].append({"id": e["card"]["id"], "nom": e["card"]["nom"], "copies": e["copies"]})

    roles = []
    for role in ROLE_ORDER:
        b = blocs.get(role)
        if not b:
            continue
        b["cartes"].sort(key=lambda x: (-x["copies"], x["nom"]))
        roles.append({"role": role, "label": ROLE_LABELS[role], **b})

    return {"total": total, "roles": roles, "alertes": _alertes(total, blocs)}


def _alertes(total: int, blocs: dict[str, dict]) -> list[dict]:
    n = lambda r: blocs.get(r, {}).get("copies", 0)  # noqa: E731
    out: list[dict] = []
    if total == 0:
        return out
    if total < 40:
        out.append({"niveau": "attention", "message": f"Main Deck à {total} cartes : 40 minimum."})
    if total >= 30 and n("starter") < 6:
        out.append({
            "niveau": "attention",
            "message": f"Seulement {n('starter')} starter(s) détecté(s) : "
                       "la plupart des decks en jouent 6 à 12 pour ouvrir régulièrement.",
        })
    if total >= 30 and n("brick") > 5:
        out.append({
            "niveau": "attention",
            "message": f"{n('brick')} cartes peuvent bloquer ta main (monstres difficiles à jouer seuls).",
        })
    if total >= 30 and n("handtrap") == 0 and n("interruption") == 0:
        out.append({
            "niveau": "info",
            "message": "Aucune interruption ni hand trap détectée : le deck ne gêne pas l'adversaire.",
        })
    if total >= 30 and n("starter") >= 6 and not any(a["niveau"] == "attention" for a in out):
        out.append({"niveau": "ok", "message": "Nombre de starters correct."})
    return out
