// apps/web/lib/ygoApi.ts
// Client typé côté front. Il ne parle JAMAIS à YGOPRODeck en direct :
// il passe par le backend FastAPI, qui sert le cache local et la logique.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// ---------- Types partagés (idéalement dans packages/types) ----------

export type Zone = "main" | "extra" | "side";
export type Format = "advanced" | "traditional" | "speed_duel" | "master_duel";
export type BanStatus = "banned" | "limited" | "semi_limited" | "unlimited";

export interface Card {
  id: number;
  nomFr: string;
  type: string;
  frameType: string;            // "effect" | "link" | "xyz" | "spell" | "trap" ...
  attribut: string | null;
  race: string | null;
  niveauRangLink: number | null;
  atk: number | null;
  def: number | null;
  effetFr: string;
  imageLocale: string;          // /cards/{id}.jpg réhébergée
  banStatus: BanStatus;         // déjà résolu (override > API) pour le format demandé
}

export interface DeckEntry {
  card: Card;
  zone: Zone;
  quantite: number;
}

// Une étape de combo, telle que consommée par le flowchart (arbre)
export interface ComboStep {
  id: string;
  parentId: string | null;      // null = racine
  cardId: number | null;
  action: string;
  explicationFr: string;
}

export interface Combo {
  id: number;
  nom: string;
  cartesRequises: number;
  resultat: string;
  steps: ComboStep[];
  realisable: boolean;          // calculé par le back : toutes les cartes-clés sont-elles dans le deck ?
}

export interface Matchup {
  deckAdverse: string;
  faveur: "favorable" | "equilibre" | "defavorable";
  conseilFr: string;
}

export interface Suggestion {
  card: Card;
  categorie: "staple" | "handtrap" | "tech" | "extra";
  raison: string;               // pourquoi cette carte entre en synergie
}

// ---------- Helpers fetch ----------

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`API ${res.status} sur ${path}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status} sur ${path}`);
  return res.json() as Promise<T>;
}

// ---------- Endpoints ----------

// Recherche floue de cartes (noms FR), filtrée par format pour le statut de banlist.
export const searchCards = (q: string, format: Format) =>
  get<Card[]>("/cards/search", { q, format });

// Combos réalisables avec le deck courant (ids de cartes en main).
export const generateCombos = (cardIds: number[], format: Format) =>
  post<Combo[]>("/combos/generate", { cardIds, format });

// Suggestions d'optimisation (staples, hand traps, tech) pour l'archétype détecté.
export const suggestCards = (cardIds: number[], format: Format) =>
  post<Suggestion[]>("/suggest", { cardIds, format });

// Matchups de l'archétype dominant du deck.
export const getMatchups = (archetypeId: number) =>
  get<Matchup[]>(`/meta/matchups`, { archetype_id: String(archetypeId) });
