// apps/web/app/deckbuilder/page.tsx
"use client";

import { useMemo, useState } from "react";
import type { Card, Format, Zone } from "@/lib/ygoApi";
import { searchCards } from "@/lib/ygoApi";
import { useDeckStore } from "@/store/deckStore";
import CardTile from "@/components/CardTile";
import AnalysisPanel from "@/components/AnalysisPanel";

const FORMATS: { value: Format; label: string }[] = [
  { value: "master_duel", label: "Master Duel" },
  { value: "advanced", label: "Advanced" },
  { value: "traditional", label: "Traditional" },
  { value: "speed_duel", label: "Speed Duel" },
];

export default function DeckbuilderPage() {
  const format = useDeckStore((s) => s.format);
  const setFormat = useDeckStore((s) => s.setFormat);
  const ajouterCarte = useDeckStore((s) => s.ajouterCarte);
  const viderDeck = useDeckStore((s) => s.viderDeck);
  const main = useDeckStore((s) => s.main);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Card[]>([]);
  const [loading, setLoading] = useState(false);

  const lancerRecherche = async () => {
    if (query.trim().length < 2) return;
    setLoading(true);
    try {
      setResults(await searchCards(query.trim(), format));
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  // IDs (avec doublons) du Main Deck pour alimenter l'analyse.
  const mainCardIds = useMemo(
    () => main.flatMap((e) => Array<number>(e.quantite).fill(e.card.id)),
    [main],
  );

  return (
    <div className="flex h-screen flex-col bg-[#0a0a0f] text-[#e6e6ef]">
      {/* En-tête */}
      <header className="scanlines flex items-center gap-4 border-b border-[#262633] bg-[#0d0d14] px-4 py-3">
        <h1 className="font-display text-lg tracking-widest text-[#22d3ee]">
          VS<span className="text-[#e84bd2]">/</span>DECKBUILDER
        </h1>
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value as Format)}
          className="rounded-md border border-[#262633] bg-[#12121a] px-2 py-1 text-sm text-[#e6e6ef] outline-none focus:border-[#22d3ee]"
        >
          {FORMATS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        <button
          onClick={viderDeck}
          className="ml-auto rounded-md border border-[#262633] px-3 py-1 text-xs uppercase tracking-wider text-[#8a8aa0] transition-colors hover:border-[#ff5a5a]/60 hover:text-[#ff5a5a]"
        >
          Vider le deck
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* COLONNE GAUCHE — Recherche */}
        <aside className="flex w-full shrink-0 flex-col border-r border-[#262633] bg-[#0d0d14] lg:w-72">
          <div className="flex gap-2 p-3">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && lancerRecherche()}
              placeholder="Rechercher une carte…"
              className="w-full rounded-md border border-[#262633] bg-[#12121a] px-3 py-1.5 text-sm outline-none focus:border-[#22d3ee]"
            />
            <button
              onClick={lancerRecherche}
              className="rounded-md bg-[#22d3ee] px-3 py-1.5 text-sm font-semibold text-[#0a0a0f] transition-opacity hover:opacity-90"
            >
              {loading ? "…" : "OK"}
            </button>
          </div>
          <div className="grid min-h-0 flex-1 grid-cols-3 content-start gap-2 overflow-y-auto p-3 pt-0 lg:grid-cols-2">
            {results.map((card) => (
              <CardTile key={card.id} card={card} onAdd={(c) => ajouterCarte(c)} />
            ))}
            {results.length === 0 && !loading && (
              <p className="col-span-full mt-4 text-xs text-[#8a8aa0]">
                Tapez un nom puis Entrée. Glissez une carte vers une zone, ou double-cliquez.
              </p>
            )}
          </div>
        </aside>

        {/* COLONNE CENTRALE — Zones du deck */}
        <main className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <DeckZone titre="Main Deck" zone="main" max={60} />
          <DeckZone titre="Extra Deck" zone="extra" max={15} />
          <DeckZone titre="Side Deck" zone="side" max={15} />
        </main>

        {/* COLONNE DROITE — Analyse */}
        <aside className="w-full shrink-0 border-l border-[#262633] lg:w-96">
          <AnalysisPanel cardIds={mainCardIds} format={format} onAddCard={(c) => ajouterCarte(c)} />
        </aside>
      </div>
    </div>
  );
}

// ---------------------------- Zone de deck -------------------------------- //
function DeckZone({ titre, zone, max }: { titre: string; zone: Zone; max: number }) {
  const entries = useDeckStore((s) => s[zone]);
  const ajouterCarte = useDeckStore((s) => s.ajouterCarte);
  const retirerCarte = useDeckStore((s) => s.retirerCarte);
  const [survol, setSurvol] = useState(false);

  const total = entries.reduce((n, e) => n + e.quantite, 0);

  return (
    <section
      onDragOver={(e) => {
        e.preventDefault();
        setSurvol(true);
      }}
      onDragLeave={() => setSurvol(false)}
      onDrop={(e) => {
        e.preventDefault();
        setSurvol(false);
        const raw = e.dataTransfer.getData("card");
        if (raw) ajouterCarte(JSON.parse(raw) as Card, zone);
      }}
      className={`rounded-lg border bg-[#0d0d14] p-3 transition-colors ${
        survol ? "border-[#22d3ee]" : "border-[#262633]"
      }`}
    >
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="font-display text-sm uppercase tracking-wider text-[#e6e6ef]">{titre}</h2>
        <span className={`text-xs font-semibold ${total > max ? "text-[#ff5a5a]" : "text-[#8a8aa0]"}`}>
          {total} / {max}
        </span>
      </div>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(58px,1fr))] gap-1.5">
        {entries.map((e) => (
          <CardTile
            key={e.card.id}
            card={e.card}
            quantite={e.quantite}
            compact
            onRemove={() => retirerCarte(e.card.id, zone)}
          />
        ))}
        {entries.length === 0 && (
          <p className="col-span-full py-3 text-xs text-[#5a5a6a]">
            Glissez des cartes ici.
          </p>
        )}
      </div>
    </section>
  );
}
