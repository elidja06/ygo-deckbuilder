"""Tests des rôles de cartes. Lancement :  python tests/test_roles.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from engine.roles import analyze_deck, classify  # noqa: E402


def c(texte, frame="effect", niveau=4):
    return {"texte": texte, "frame_type": frame, "niveau": niveau}


def test_ash_blossom_is_handtrap_and_interruption():
    t = ("When a card or effect is activated that includes any of these effects "
         "(Quick Effect): You can discard this card; negate that effect.")
    assert classify(c(t)) == ["handtrap", "interruption"]


def test_maxx_c_french_is_handtrap_and_draw_without_removal():
    t = ("Si votre adversaire Invoque Spécialement un ou plusieurs monstres (Effet Rapide) : "
         "Vous pouvez envoyer cette carte de votre main au Cimetière ; piochez 1 carte.")
    r = classify(c(t))
    assert "handtrap" in r and "draw" in r and "removal" not in r


def test_searcher_is_starter_french_and_english():
    en = 'If this card is Normal Summoned: You can add 1 "Vanquish Soul" monster from your Deck to your hand.'
    fr = "Vous pouvez ajouter 1 monstre « Âme du Vainqueur » de votre Deck à votre main."
    assert "starter" in classify(c(en)) and "starter" in classify(c(fr))


def test_self_summon_is_extender():
    assert "extender" in classify(c("You can Special Summon this card from your hand."))
    assert "extender" in classify(c("Special Summon 1 monster from your GY."))


def test_removal_and_board_breaker():
    assert "removal" in classify(c("Destroy 1 card your opponent controls.", "spell"))
    r = classify(c("Destroy all monsters your opponent controls.", "spell"))
    assert "boardbreaker" in r and "removal" in r


def test_brick_conditional_monster_and_high_level_vanilla():
    t = "Cannot be Normal Summoned/Set. Must first be Special Summoned by banishing 2 monsters."
    assert "brick" in classify(c(t, niveau=8))
    assert classify(c("", "normal", 8)) == ["brick"]
    assert "brick" not in classify(c("You can Special Summon this card from your hand.", niveau=8))


def test_extra_deck_and_plain_card_have_no_brick():
    assert "brick" not in classify(c("", "synchro", 8))
    assert classify(c("Gains 300 ATK.")) == ["autre"]


def test_analyze_deck_counts_copies_and_alerts():
    s = 'You can add 1 "X" monster from your Deck to your hand.'
    deck = [{"id": 1, "nom": "Starter A", "frame_type": "effect", "niveau": 4, "texte": s}] * 3
    deck += [{"id": 2, "nom": "Rien", "frame_type": "normal", "niveau": 4, "texte": ""}] * 40
    r = analyze_deck(deck)
    assert r["total"] == 43
    starters = next(x for x in r["roles"] if x["role"] == "starter")
    assert starters["copies"] == 3 and starters["cartes"][0] == {"id": 1, "nom": "Starter A", "copies": 3}
    assert any("starter" in a["message"] for a in r["alertes"])
    assert analyze_deck([]) == {"total": 0, "roles": [], "alertes": []}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("OK ", fn.__name__)
    print(f"{len(fns)} tests passés")
