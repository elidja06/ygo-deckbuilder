-- =====================================================================
--  Ajouts au schéma initial (schema.sql) requis par le backend Python
-- =====================================================================

-- 1) Statut de banlist API stocké localement (base du COALESCE de banlist.py).
ALTER TABLE cards ADD COLUMN IF NOT EXISTS ban_tcg VARCHAR(16);
ALTER TABLE cards ADD COLUMN IF NOT EXISTS ban_ocg VARCHAR(16);

-- 1b) Langue de la carte : 'fr' (traduite) ou 'en' (non traduite, vignette EN).
ALTER TABLE cards ADD COLUMN IF NOT EXISTS langue VARCHAR(2) DEFAULT 'fr';

-- 1c) Nom anglais (recherche en anglais) + index de recherche floue.
ALTER TABLE cards ADD COLUMN IF NOT EXISTS nom_en TEXT;
CREATE INDEX IF NOT EXISTS idx_cards_nom_en_trgm ON cards USING gin (nom_en gin_trgm_ops);

-- 2) Pools de suggestion (à pré-remplir à la main).
CREATE TABLE IF NOT EXISTS staples (
    id       SERIAL PRIMARY KEY,
    card_id  INTEGER NOT NULL REFERENCES cards(id),
    format   TEXT NOT NULL,
    UNIQUE (card_id, format)
);

CREATE TABLE IF NOT EXISTS hand_traps (
    id        SERIAL PRIMARY KEY,
    card_id   INTEGER NOT NULL UNIQUE REFERENCES cards(id),
    priorite  SMALLINT NOT NULL DEFAULT 0      -- pertinence décroissante
);

CREATE TABLE IF NOT EXISTS tech_cards (
    id            SERIAL PRIMARY KEY,
    card_id       INTEGER NOT NULL REFERENCES cards(id),
    archetype_id  INTEGER NOT NULL REFERENCES archetypes(id),
    raison        TEXT NOT NULL,
    UNIQUE (card_id, archetype_id)
);

-- 3) Suivi de version du worker.
CREATE TABLE IF NOT EXISTS sync_state (
    id               INTEGER PRIMARY KEY,           -- toujours = 1
    last_db_version  VARCHAR(64),
    synced_at        TIMESTAMPTZ
);
