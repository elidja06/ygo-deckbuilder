// apps/web/lib/ygoApi.ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export type Zone = "main" | "extra" | "side";
export type Format = "advanced" | "traditional" | "speed_duel" | "master_duel";
export type BanStatus = "banned" | "limited" | "semi_limited" | "unlimited";

export interface Card {
  id: number;
  nomFr: string;
  type: string;
  frameType: string;
  attribut: string | null;
  race: string | null;
  niveauRangLink: number | null;
  atk: number | null;
  def: number | null;
  effetFr: string;
  imageLocale: string;
  /** "fr" (traduite) ou "en" (non traduite) — affiche la vignette EN */
  langue?: "fr" | "en";
  banStatus: BanStatus;
}

export interface DeckEntry {
  card: Card;
  zone: Zone;
  quantite: number;
}

export interface ComboStep {
  id: string;
  parentId: string | null;
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
  realisable: boolean;
}

export interface Matchup {
  deckAdverse: string;
  faveur: "favorable" | "equilibre" | "defavorable";
  conseilFr: string;
}

export interface Suggestion {
  card: Card;
  categorie: "staple" | "handtrap" | "tech" | "extra";
  raison: string;
}

// ---------- Helpers fetch ----------
// window.location.origin permet d'utiliser une base relative ("/api").

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const base =
    typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  const url = new URL(`${API_BASE}${path}`, base);
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

/** Recherche par nom. `types` = natures séparées par des virgules (spell,trap,fusion…). */
export const searchCards = (q: string, format: Format, types?: string) =>
  get<Card[]>("/cards/search", {
    q,
    format,
    ...(types ? { types } : {}),
  });

/** Toutes les cartes du même archétype — bouton « Cartes liées ». */
export const fetchRelatedCards = (cardId: number, format: Format) =>
  get<Card[]>("/cards/by-archetype", { card_id: String(cardId), format });

export const generateCombos = (cardIds: number[], format: Format) =>
  post<Combo[]>("/combos/generate", { cardIds, format });

export const suggestCards = (cardIds: number[], format: Format) =>
  post<Suggestion[]>("/suggest", { cardIds, format });

export const getMatchups = (archetypeId: number) =>
  get<Matchup[]>("/meta/matchups", { archetype_id: String(archetypeId) });

export const fetchMatchupsForDeck = (cardIds: number[], format: Format) =>
  post<Matchup[]>("/meta/matchups/by-deck", { cardIds, format });