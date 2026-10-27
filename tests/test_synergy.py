"""Tests du moteur de synergie (textes fictifs). Lancement :  python tests/test_synergy.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from engine.synergy import (  # noqa: E402
    WEIGHT_NAME,
    WEIGHT_THEME,
    build_edges,
    extract_quoted,
    normalize,
)

CARDS = [
    {"id": 1, "name": "Sky Wolf Alpha", "text": 'Add 1 "Sky Wolf" monster from your Deck to your hand.'},
    {"id": 2, "name": "Sky Wolf Beta", "text": "Special Summon this card. You can banish \"Sky Wolf Alpha\" from your GY."},
    {"id": 3, "name": "Sky Wolf Gamma", "text": "Gains 300 ATK."},
    {"id": 4, "name": "Hand Eraser", "text": 'Discard this card; negate the effect. Cannot be used with "Hand".'},
    {"id": 5, "name": "Moon Blade", "text": "Pas de citation ici."},
]


def edges_by_pair(edges):
    return {(e["source_id"], e["target_id"]): e for e in edges}


def test_extract_quoted_handles_all_quote_styles():
    txt = "Ajoutez « Âme du Vainqueur » ou \"Razen\" ou “Rock of Light”."
    assert extract_quoted(txt) == ["âme du vainqueur", "razen", "rock of light"]


def test_extract_quoted_dedupes_and_handles_empty():
    assert extract_quoted(None) == []
    assert extract_quoted('"A B" et "a b"') == ["a b"]


def test_normalize_apostrophes_and_case():
    assert normalize("L’Étoile  Noire") == "l'étoile noire"


def test_name_reference_creates_weight_one_edge():
    e = edges_by_pair(build_edges(CARDS))
    assert e[(2, 1)]["kind"] == "name"
    assert e[(2, 1)]["weight"] == WEIGHT_NAME


def test_theme_reference_links_all_matching_cards_but_not_self():
    e = edges_by_pair(build_edges(CARDS))
    # "Sky Wolf" cité par la carte 1 : touche 2 et 3 (thème), pas 1 elle-même
    assert e[(1, 2)]["kind"] == "theme" and e[(1, 2)]["weight"] == WEIGHT_THEME
    assert e[(1, 3)]["kind"] == "theme"
    assert (1, 1) not in e


def test_short_fragments_are_ignored():
    # "Hand" fait 4 lettres mais ne correspond qu'à 1 nom ("Hand Eraser") : pas un thème
    e = edges_by_pair(build_edges(CARDS))
    assert (4, 4) not in e
    assert not any(src == 4 for src, _ in e)


def test_generic_fragment_is_dropped():
    cards = [{"id": i, "name": f"Dragon {i}", "text": ""} for i in range(1, 100)]
    cards.append({"id": 1000, "name": "Caller", "text": 'Add a "Dragon" monster.'})
    assert not any(e["source_id"] == 1000 for e in build_edges(cards))


def test_no_citation_no_edge():
    assert not any(e["source_id"] == 5 for e in build_edges(CARDS))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("OK ", fn.__name__)
    print(f"{len(fns)} tests passés")
