"""Tests du module de noms français. Lancement :  python tests/test_frnames.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from engine.frnames import parse_fr_name, resolve_batch  # noqa: E402

RAZEN = "{{CardTable2\n| fr_name             = Âme du Vainqueur Razen\n| de_name             = Bezwingerseele Razen\n| it_name = X\n}}"


def test_parse_fr_name_reads_padded_field():
    assert parse_fr_name(RAZEN) == "Âme du Vainqueur Razen"


def test_parse_fr_name_absent_or_empty():
    assert parse_fr_name(None) is None
    assert parse_fr_name("{{CardTable2\n| de_name = X\n}}") is None
    assert parse_fr_name("{{CardTable2\n| fr_name = \n| de_name = X\n}}") is None


def test_parse_fr_name_cleans_wikimarkup():
    txt = "| fr_name = [[Âme du Vainqueur]]<br />Test\n"
    assert parse_fr_name(txt) == "Âme du Vainqueur Test"


def _page(title, content):
    return {"title": title, "revisions": [{"slots": {"main": {"content": content}}}]}


def test_resolve_batch_handles_normalization_redirect_and_missing():
    payload = {
        "query": {
            "normalized": [{"from": "stake_your_Soul!", "to": "Stake your Soul!"}],
            "redirects": [{"from": "Stake your Soul!", "to": "Stake Your Soul!"}],
            "pages": [
                _page("Vanquish Soul Razen", RAZEN),
                _page("Stake Your Soul!", "| fr_name = Misez Votre Âme !\n"),
                _page("No French", "| de_name = X\n"),
                {"title": "Ghost", "missing": True},
            ],
        }
    }
    titles = ["Vanquish Soul Razen", "stake_your_Soul!", "No French", "Ghost", "Unknown"]
    res = resolve_batch(titles, payload)
    assert res["Vanquish Soul Razen"] == "Âme du Vainqueur Razen"
    assert res["stake_your_Soul!"] == "Misez Votre Âme !"
    assert res["No French"] is None
    assert res["Ghost"] is None
    assert res["Unknown"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("OK ", fn.__name__)
    print(f"{len(fns)} tests passés")
