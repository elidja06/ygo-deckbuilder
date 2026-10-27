"""Tests de l'extraction Master Duel. Lancement :  python tests/test_mdcards.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from engine.mdcards import extract_md_rarities  # noqa: E402


def test_extracts_only_cards_with_md_rarity():
    data = [
        {"id": 1, "misc_info": [{"md_rarity": "Ultra Rare"}]},
        {"id": 2, "misc_info": [{"has_effect": 1}]},       # absente de Master Duel
        {"id": 3},                                          # pas de misc_info
        {"id": "4", "misc_info": [{}, {"md_rarity": "Common"}]},
    ]
    assert extract_md_rarities(data) == {1: "Ultra Rare", 4: "Common"}


def test_empty_dump():
    assert extract_md_rarities([]) == {}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("OK ", fn.__name__)
    print(f"{len(fns)} tests passés")
