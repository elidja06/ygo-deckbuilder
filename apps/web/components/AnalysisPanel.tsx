// apps/web/components/AnalysisPanel.tsx
"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import type { Card, Combo, DeckAnalysis, Format, Matchup, Suggestion } from "@/lib/ygoApi";
import {
  analyzeDeck,
  fetchMatchupsForDeck,
  generateCombos,
  suggestCards,
} from "@/lib/ygoApi";

// React Flow ne tourne qu'au client → import dynamique sans SSR.
const ComboFlowchart = dynamic(() => import("@/components/ComboFlowchart"), {
  ssr: false,
  loading: () => <p className="p-4 text-xs text-[#8a8aa0]">Chargement du schéma…</p>,
});

type Onglet = "analyse" | "suggestions" | "combos" | "matchups";

interface Props {
  cardIds: number[];
  format: Format;
  onAddCard: (card: Card) => void;
}

const CATEGORIES: { id: Suggestion["categorie"]; label: string }[] = [
  { id: "synergie", label: "Synergies" },
  { id: "staple", label: "Staples" },
  { id: "handtrap", label: "Hand Traps" },
  { id: "tech", label: "Tech Cards" },
];

const FAVEUR_STYLE: Record<Matchup["faveur"], { dot: string; texte: string; label: string }> = {
  favorable: { dot: "#36d399", texte: "#36d399", label: "Favorable" },
  equilibre: { dot: "#ffb020", texte: "#ffb020", label: "Équilibré" },
  defavorable: { dot: "#ff5a5a", texte: "#ff5a5a", label: "Défavorable" },
};

export default function AnalysisPanel({ cardIds, format, onAddCard }: Props) {
  const [onglet, setOnglet] = useState<Onglet>("analyse");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [combos, setCombos] = useState<Combo[]>([]);
  const [matchups, setMatchups] = useState<Matchup[]>([]);
  const [analyse, setAnalyse] = useState<DeckAnalysis | null>(null);
  const [chargement, setChargement] = useState(false);

  const signature = cardIds.join(",") + "|" + format;

  // L'onglet Combos n'apparaît que s'il existe des combos pour l'archétype du deck.
  const onglets: Onglet[] = [
    "analyse",
    "suggestions",
    ...(combos.length > 0 ? (["combos"] as Onglet[]) : []),
    "matchups",
  ];
  const ongletActif: Onglet = onglets.includes(onglet) ? onglet : "analyse";

  // Recalcul à chaque modification du deck (anti-rebond 450 ms).
  useEffect(() => {
    if (cardIds.length === 0) {
      setAnalyse(null);
      setSuggestions([]);
      setCombos([]);
      setMatchups([]);
      return;
    }
    const t = setTimeout(async () => {
      setChargement(true);
      try {
        const [a, s, c, m] = await Promise.all([
          analyzeDeck(cardIds, format),
          suggestCards(cardIds, format),
          generateCombos(cardIds, format),
          fetchMatchupsForDeck(cardIds, format),
        ]);
        setAnalyse(a);
        setSuggestions(s);
        setCombos(c);
        setMatchups(m);
      } catch {
        /* on garde l'affichage précédent en cas d'échec réseau */
      } finally {
        setChargement(false);
      }
    }, 450);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  return (
    <div className="flex h-full flex-col bg-[#12121a]">
      {/* Onglets */}
      <div className="flex border-b border-[#262633]">
        {onglets.map((o) => (
          <button
            key={o}
            onClick={() => setOnglet(o)}
            className={`flex-1 px-2 py-2.5 font-display text-[11px] uppercase tracking-wider transition-colors ${
              ongletActif === o
                ? "border-b-2 border-[#22d3ee] text-[#22d3ee]"
                : "text-[#8a8aa0] hover:text-[#e6e6ef]"
            }`}
          >
            {o === "analyse"
              ? "Analyse"
              : o === "suggestions"
                ? "Suggestions"
                : o === "combos"
                  ? "Combos"
                  : "Matchups"}
          </button>
        ))}
      </div>

      {/* Barre d'état */}
      <div className="h-0.5 w-full overflow-hidden bg-transparent">
        {chargement && <div className="h-full w-full animate-pulse bg-[#22d3ee]/60" />}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {cardIds.length === 0 ? (
          <p className="mt-8 text-center text-xs text-[#8a8aa0]">
            Ajoutez des cartes au Main Deck pour lancer l'analyse.
          </p>
        ) : ongletActif === "analyse" ? (
          <AnalyseTab analyse={analyse} />
        ) : ongletActif === "suggestions" ? (
          <SuggestionsTab suggestions={suggestions} onAddCard={onAddCard} />
        ) : ongletActif === "combos" ? (
          <CombosTab combos={combos} />
        ) : (
          <MatchupsTab matchups={matchups} />
        )}
      </div>
    </div>
  );
}

// ------------------------------- Analyse ---------------------------------- //
const ALERTE_STYLE: Record<DeckAnalysis["alertes"][number]["niveau"], { couleur: string; icone: string }> = {
  attention: { couleur: "#ffb020", icone: "!" },
  info: { couleur: "#22d3ee", icone: "i" },
  ok: { couleur: "#36d399", icone: "✓" },
};

function AnalyseTab({ analyse }: { analyse: DeckAnalysis | null }) {
  if (!analyse) return <p className="text-xs text-[#8a8aa0]">Analyse en cours…</p>;

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-[#8a8aa0]">
        Main Deck : <b className="text-[#e6e6ef]">{analyse.total}</b> cartes. Rôles déduits du
        texte des effets (indicatif : une carte peut avoir plusieurs rôles).
      </p>

      {analyse.alertes.length > 0 && (
        <div className="space-y-1.5">
          {analyse.alertes.map((a, i) => {
            const st = ALERTE_STYLE[a.niveau];
            return (
              <div
                key={i}
                className="flex gap-2 rounded-md border bg-[#1a1a24] p-2 text-[12px] leading-snug text-[#b9b9cc]"
                style={{ borderColor: st.couleur + "66" }}
              >
                <span className="font-bold" style={{ color: st.couleur }}>
                  {st.icone}
                </span>
                <span>{a.message}</span>
              </div>
            );
          })}
        </div>
      )}

      {analyse.roles.map((r) => (
        <section key={r.role}>
          <h3 className="mb-1.5 flex items-baseline justify-between font-display text-[11px] uppercase tracking-widest text-[#22d3ee]">
            <span>{r.label}</span>
            <span className="text-[#e6e6ef]">{r.copies}</span>
          </h3>
          <p className="text-[12px] leading-relaxed text-[#b9b9cc]">
            {r.cartes.map((c) => (c.copies > 1 ? `${c.nom} ×${c.copies}` : c.nom)).join(" · ")}
          </p>
        </section>
      ))}
    </div>
  );
}

// ----------------------------- Suggestions -------------------------------- //
function SuggestionsTab({
  suggestions,
  onAddCard,
}: {
  suggestions: Suggestion[];
  onAddCard: (card: Card) => void;
}) {
  if (suggestions.length === 0)
    return <p className="text-xs text-[#8a8aa0]">Aucune suggestion pour ce deck.</p>;

  return (
    <div className="space-y-5">
      {CATEGORIES.map(({ id, label }) => {
        const items = suggestions.filter((s) => s.categorie === id);
        if (items.length === 0) return null;
        return (
          <section key={id}>
            <h3 className="mb-2 font-display text-[11px] uppercase tracking-widest text-[#22d3ee]">
              {label}
            </h3>
            <div className="space-y-1.5">
              {items.map((s) => (
                <button
                  key={s.card.id}
                  onClick={() => onAddCard(s.card)}
                  className="group flex w-full items-center gap-2.5 rounded-md border border-[#262633] bg-[#1a1a24] p-1.5 text-left transition-colors hover:border-[#22d3ee]/60"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={s.card.imageLocale}
                    alt={s.card.nomFr}
                    className="h-12 w-[33px] shrink-0 rounded object-cover"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium text-[#e6e6ef]">
                      {s.card.nomFr}
                    </span>
                    <span className="block truncate text-[11px] text-[#8a8aa0]">{s.raison}</span>
                  </span>
                  <span className="shrink-0 text-lg leading-none text-[#8a8aa0] transition-colors group-hover:text-[#22d3ee]">
                    +
                  </span>
                </button>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

// -------------------------------- Combos ---------------------------------- //
function CombosTab({ combos }: { combos: Combo[] }) {
  if (combos.length === 0)
    return (
      <p className="text-xs text-[#8a8aa0]">
        Aucun combo connu pour l'archétype détecté.
      </p>
    );

  return (
    <div className="space-y-4">
      {combos.map((combo) => (
        <div key={combo.id} className="rounded-lg border border-[#262633] bg-[#1a1a24] p-3">
          <div className="mb-1 flex items-center gap-2">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: combo.realisable ? "#36d399" : "#5a5a6a" }}
            />
            <h3 className="font-display text-sm text-[#e6e6ef]">{combo.nom}</h3>
          </div>
          <p className="mb-2 text-[11px] text-[#8a8aa0]">
            {combo.cartesRequises} carte{combo.cartesRequises > 1 ? "s" : ""} requise
            {combo.cartesRequises > 1 ? "s" : ""}
            {!combo.realisable && " · pièces manquantes dans le deck"}
          </p>

          {combo.realisable ? (
            <ComboFlowchart combo={combo} />
          ) : (
            <p className="rounded border border-dashed border-[#3a3a46] p-3 text-[11px] text-[#8a8aa0]">
              Complétez les cartes de départ pour visualiser le schéma.
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

// ------------------------------- Matchups --------------------------------- //
function MatchupsTab({ matchups }: { matchups: Matchup[] }) {
  if (matchups.length === 0)
    return <p className="text-xs text-[#8a8aa0]">Aucun matchup référencé.</p>;

  return (
    <div className="space-y-2">
      {matchups.map((m) => {
        const st = FAVEUR_STYLE[m.faveur];
        return (
          <div key={m.deckAdverse} className="rounded-md border border-[#262633] bg-[#1a1a24] p-2.5">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="font-display text-sm text-[#e6e6ef]">{m.deckAdverse}</span>
              <span className="flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: st.texte }}>
                <span className="h-2 w-2 rounded-full" style={{ background: st.dot }} />
                {st.label}
              </span>
            </div>
            <p className="text-[12px] leading-snug text-[#b9b9cc]">{m.conseilFr}</p>
          </div>
        );
      })}
    </div>
  );
}
