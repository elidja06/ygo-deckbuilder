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


def test_alt_names_let_english_text_link_french_named_cards():
    # Cartes renommées en français, texte resté anglais : le nom anglais sert de repli.
    cards = [
        {"id": 1, "name": "Loup du Ciel Alpha", "alt_names": ["Sky Wolf Alpha"],
         "text": 'Add 1 "Sky Wolf" monster from your Deck to your hand.'},
        {"id": 2, "name": "Loup du Ciel Beta", "alt_names": ["Sky Wolf Beta"],
         "text": 'Banish "Sky Wolf Alpha" from your GY.'},
        {"id": 3, "name": "Loup du Ciel Gamma", "alt_names": ["Sky Wolf Gamma"], "text": ""},
    ]
    e = edges_by_pair(build_edges(cards))
    assert e[(2, 1)]["kind"] == "name"        # nom anglais exact
    assert e[(1, 2)]["kind"] == "theme" and e[(1, 3)]["kind"] == "theme"
    assert len([k for k in e if k[0] == 1]) == 2   # pas de doublons malgré 2 formes de nom


def test_score_order_name_mutual_archetype_theme():
    from engine.synergy import describe_partner, score_partners

    sortants = [(10, "name", 1.0), (11, "theme", 0.5), (12, "theme", 0.5)]
    entrants = [(10, "name", 1.0), (11, "theme", 0.5), (13, "theme", 0.5)]
    # 20 : même archétype seulement ; 12 : cité par la carte (thème) ; 13 : la cite (thème)
    p = score_partners(sortants, entrants, [20])
    s = {pid: describe_partner(v) for pid, v in p.items()}
    assert s[10]["score"] == 1.25 and s[10]["sens"] == "mutuel"      # nom cité, mutuel
    assert s[11]["score"] == 0.75 and s[11]["sens"] == "mutuel"      # thème mutuel
    assert s[20]["score"] == 0.6 and s[20]["sens"] == "archetype"    # archétype seul
    assert s[12]["score"] == 0.5 and s[13]["score"] == 0.5           # thème simple
    ordre = sorted(s, key=lambda k: -s[k]["score"])
    assert ordre[:3] == [10, 11, 20]


def test_text_link_plus_archetype_gets_bonus_and_keeps_name_kind():
    from engine.synergy import describe_partner, score_partners

    p = score_partners([(1, "theme", 0.5)], [], [1, 2])
    d1, d2 = describe_partner(p[1]), describe_partner(p[2])
    assert d1["score"] == 0.7 and d1["memeArchetype"] is True and d1["kind"] == "archetype"
    assert d2["score"] == 0.6 and d2["sens"] == "archetype"
    p = score_partners([(1, "name", 1.0)], [], [1])
    assert describe_partner(p[1])["kind"] == "name"


def test_no_signal_gives_empty():
    from engine.synergy import score_partners

    assert score_partners([], [], []) == {}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("OK ", fn.__name__)
    print(f"{len(fns)} tests passés")
