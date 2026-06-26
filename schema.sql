-- =====================================================================
--  Deckbuilder Yu-Gi-Oh! — Schéma PostgreSQL
--  Cache de cartes + decks + combos + matchups + override de banlist
-- =====================================================================

-- Archétypes : pivot central de la connaissance (combos & matchups y sont rattachés)
CREATE TABLE archetypes (
    id      SERIAL PRIMARY KEY,
    nom     TEXT NOT NULL UNIQUE          -- ex. "Vanquish Soul", "Zoodiaque"
);

-- Cartes : miroir local de l'API YGOPRODeck (langue = fr)
CREATE TABLE cards (
    id                  INTEGER PRIMARY KEY,          -- passcode 8 chiffres (clé de l'API)
    archetype_id        INTEGER REFERENCES archetypes(id) ON DELETE SET NULL,
    nom_fr              TEXT NOT NULL,
    type                TEXT NOT NULL,                -- "Effect Monster", "Spell Card", "Link Monster"...
    frame_type          TEXT,                         -- "effect", "link", "xyz", "spell", "trap"...
    attribut            TEXT,                         -- DARK, LIGHT, ... (NULL pour magies/pièges)
    race                TEXT,                         -- type au sens FR : Guerrier, Magicien, Continu...
    niveau_rang_link    SMALLINT,                     -- Niveau OU Rang OU valeur Link
    atk                 INTEGER,
    def                 INTEGER,                       -- NULL pour les Link
    effet_fr            TEXT,
    image_locale        TEXT,                         -- chemin réhébergé : /cards/{id}.jpg
    api_updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_cards_archetype ON cards(archetype_id);
CREATE INDEX idx_cards_nom_trgm  ON cards USING gin (nom_fr gin_trgm_ops); -- recherche floue (CREATE EXTENSION pg_trgm)

-- Decks de l'utilisateur
CREATE TABLE decks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nom         TEXT NOT NULL,
    format      TEXT NOT NULL DEFAULT 'master_duel'   -- advanced | traditional | speed_duel | master_duel
                CHECK (format IN ('advanced','traditional','speed_duel','master_duel')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Liaison deck <-> cartes : porte la ZONE et la QUANTITÉ
CREATE TABLE deck_cards (
    id          SERIAL PRIMARY KEY,
    deck_id     UUID    NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id     INTEGER NOT NULL REFERENCES cards(id),
    zone        TEXT    NOT NULL CHECK (zone IN ('main','extra','side')),
    quantite    SMALLINT NOT NULL DEFAULT 1 CHECK (quantite BETWEEN 1 AND 3),
    UNIQUE (deck_id, card_id, zone)
);
CREATE INDEX idx_deckcards_deck ON deck_cards(deck_id);

-- Combos : rattachés à l'archétype, réutilisables sur tous les decks concernés
CREATE TABLE combos (
    id              SERIAL PRIMARY KEY,
    archetype_id    INTEGER NOT NULL REFERENCES archetypes(id) ON DELETE CASCADE,
    nom             TEXT NOT NULL,                    -- ex. "Démarrage 1 carte -> Apollousa"
    cartes_requises INTEGER NOT NULL DEFAULT 1,       -- nb de cartes en main pour amorcer
    resultat        TEXT                              -- board final visé
);

-- Étapes ordonnées d'un combo -> alimente directement le flowchart React Flow
CREATE TABLE combo_steps (
    id              SERIAL PRIMARY KEY,
    combo_id        INTEGER NOT NULL REFERENCES combos(id) ON DELETE CASCADE,
    card_id         INTEGER REFERENCES cards(id),     -- carte impliquée (NULL = étape logique pure)
    ordre           SMALLINT NOT NULL,                -- position dans l'arbre
    parent_step_id  INTEGER REFERENCES combo_steps(id),-- NULL = racine ; sinon = branche (arbre)
    action          TEXT NOT NULL,                    -- "invocation_normale", "activation_effet", "tuto"...
    explication_fr  TEXT NOT NULL,                    -- texte clair débutant/confirmé
    UNIQUE (combo_id, ordre)
);

-- Matchups : favorable/défavorable + conseil rapide, par archétype
CREATE TABLE matchups (
    id              SERIAL PRIMARY KEY,
    archetype_id    INTEGER NOT NULL REFERENCES archetypes(id) ON DELETE CASCADE,
    deck_adverse    TEXT NOT NULL,                    -- ex. "Ryzeal", "Tenpai Dragon"
    faveur          TEXT NOT NULL CHECK (faveur IN ('favorable','equilibre','defavorable')),
    conseil_fr      TEXT
);

-- Override de banlist : corrige la banlist Master Duel quand l'API est en retard
CREATE TABLE banlist_overrides (
    id          SERIAL PRIMARY KEY,
    card_id     INTEGER NOT NULL REFERENCES cards(id),
    format      TEXT NOT NULL,                        -- 'master_duel' en priorité
    statut      TEXT NOT NULL CHECK (statut IN ('banned','limited','semi_limited','unlimited')),
    source      TEXT,                                 -- note : date de banlist, ex. "MD 2026-05"
    UNIQUE (card_id, format)
);

-- Statut effectif d'une carte dans un format = override s'il existe, sinon donnée API.
-- (À résoudre côté FastAPI : LEFT JOIN banlist_overrides puis COALESCE.)
