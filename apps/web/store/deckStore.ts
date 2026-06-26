// apps/web/store/deckStore.ts
import { create } from "zustand";
import type { BanStatus, Card, DeckEntry, Format, Zone } from "@/lib/ygoApi";

const EXTRA_FRAMES = new Set(["fusion", "synchro", "xyz", "link"]);
const TAILLE_MAX: Record<Zone, number> = { main: 60, extra: 15, side: 15 };
const ZONES: Zone[] = ["main", "extra", "side"];

/** Zone d'accueil par défaut selon le type de carte. */
export const zoneParDefaut = (card: Card): Zone =>
  EXTRA_FRAMES.has(card.frameType) ? "extra" : "main";

/** Une carte Extra ne va que dans l'Extra Deck, et inversement. */
export const zoneAutorisee = (card: Card, zone: Zone): boolean =>
  EXTRA_FRAMES.has(card.frameType) ? zone === "extra" : zone !== "extra";

/** Nombre d'exemplaires autorisés selon le statut de banlist. */
const plafondBanlist = (s: BanStatus): number =>
  s === "banned" ? 0 : s === "limited" ? 1 : s === "semi_limited" ? 2 : 3;

interface DeckState {
  format: Format;
  main: DeckEntry[];
  extra: DeckEntry[];
  side: DeckEntry[];
  setFormat: (f: Format) => void;
  ajouterCarte: (card: Card, zone?: Zone) => void;
  retirerCarte: (cardId: number, zone: Zone) => void;
  viderDeck: () => void;
}

export const useDeckStore = create<DeckState>((set, get) => ({
  format: "master_duel",
  main: [],
  extra: [],
  side: [],

  setFormat: (format) => set({ format }),

  ajouterCarte: (card, zone) => {
    const cible = zone ?? zoneParDefaut(card);
    if (!zoneAutorisee(card, cible)) return;

    const state = get();

    // Le plafond de 3 (ou banlist) s'applique TOUTES zones confondues.
    const copiesTotales = ZONES.reduce(
      (n, z) =>
        n + state[z].filter((e) => e.card.id === card.id).reduce((m, e) => m + e.quantite, 0),
      0,
    );
    if (copiesTotales >= plafondBanlist(card.banStatus)) return;

    // Limite de taille de la zone (60 / 15 / 15).
    const tailleZone = state[cible].reduce((n, e) => n + e.quantite, 0);
    if (tailleZone >= TAILLE_MAX[cible]) return;

    const zoneArr = state[cible];
    const existant = zoneArr.find((e) => e.card.id === card.id);
    const maj: DeckEntry[] = existant
      ? zoneArr.map((e) =>
          e.card.id === card.id ? { ...e, quantite: e.quantite + 1 } : e,
        )
      : [...zoneArr, { card, zone: cible, quantite: 1 }];

    set({ [cible]: maj } as Partial<DeckState>);
  },

  retirerCarte: (cardId, zone) =>
    set(
      (state) =>
        ({
          [zone]: state[zone].flatMap((e) =>
            e.card.id !== cardId
              ? [e]
              : e.quantite > 1
                ? [{ ...e, quantite: e.quantite - 1 }]
                : [],
          ),
        }) as Partial<DeckState>,
    ),

  viderDeck: () => set({ main: [], extra: [], side: [] }),
}));
