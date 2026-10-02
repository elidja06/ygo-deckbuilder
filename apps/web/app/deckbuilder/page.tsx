// apps/web/app/deckbuilder/page.tsx
"use client";

import { useMemo, useState } from "react";
import type { Card, Format, Zone } from "@/lib/ygoApi";
import { fetchRelatedCards, searchCards } from "@/lib/ygoApi";
import { useDeckStore } from "@/store/deckStore";
import CardTile from "@/components/CardTile";
import AnalysisPanel from "@/components/AnalysisPanel";

const FORMATS: { value: Format; label: string }[] = [
  { value: "master_duel", label: "Master Duel" },
  { value: "advanced", label: "Advanced" },
  { value: "traditional", label: "Traditional" },
  { value: "speed_duel", label: "Speed Duel" },
];

// Filtres de nature de carte (valeurs envoyées à l'API).
const TYPES: { id: string; label: string }[] = [
  { id: "normal", label: "Normal" },
  { id: "effect", label: "Effet" },
  { id: "ritual", label: "Rituel" },
  { id: "fusion", label: "Fusion" },
  { id: "synchro", label: "Synchro" },
  { id: "xyz", label: "Xyz" },
  { id: "link", label: "Lien" },
  { id: "pendulum", label: "Pendule" },
  { id: "spell", label: "Magie" },
  { id: "trap", label: "Piège" },
];

export default function DeckbuilderPage() {
  const format = useDeckStore((s) => s.format);
  const setFormat = useDeckStore((s) => s.setFormat);
  const ajouterCarte = useDeckStore((s) => s.ajouterCarte);
  const viderDeck = useDeckStore((s) => s.viderDeck);
  const main = useDeckStore((s) => s.main);

  const [query, setQuery] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [results, setResults] = useState<Card[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [titreResultats, setTitreResultats] = useState("Résultats");

  const toggleType = (id: string) =>
    setTypes((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));

  const lancerRecherche = async (q = query, t = types) => {
    if (q.trim().length < 2) return;
    setLoading(true);
    setSelected(null);
    try {
      const data = await searchCards(q.trim(), format, t.length ? t.join(",") : undefined);
      setResults(data);
      setTitreResultats(`Résultats (${data.length})`);
    } catch {
      setResults([]);
      setTitreResultats("Résultats (0)");
    } finally {
      setLoading(false);
    }
  };

  const afficherCartesLiees = async (card: Card) => {
    setLoading(true);
    try {
      const data = await fetchRelatedCards(card.id, format);
      setResults(data);
      setTitreResultats(
        data.length ? `Cartes liées à ${card.nomFr} (${data.length})` : "Aucun archétype",
      );
      setSelected(null);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const mainCardIds = useMemo(
    () => main.flatMap((e) => Array<number>(e.quantite).fill(e.card.id)),
    [main],
  );

  return (
    <div className="flex h-screen flex-col bg-[#0a0a0f] text-[#e6e6ef]">
      <header className="scanlines flex items-center gap-4 border-b border-[#262633] bg-[#0d0d14] px-4 py-3">
        <h1 className="font-display text-lg tracking-widest text-[#22d3ee]">
          VS<span className="text-[#e84bd2]">/</span>DECKBUILDER
        </h1>
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value as Format)}
          className="rounded-md border border-[#262633] bg-[#12121a] px-2 py-1 text-sm outline-none focus:border-[#22d3ee]"
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
        {/* ---------------- Colonne gauche : recherche ---------------- */}
        <aside className="flex w-full shrink-0 flex-col border-r border-[#262633] bg-[#0d0d14] lg:w-[25rem]">
          <div className="flex gap-2 p-3">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && lancerRecherche()}
              placeholder="Rechercher une carte…"
              className="w-full rounded-md border border-[#262633] bg-[#12121a] px-3 py-2 text-sm outline-none focus:border-[#22d3ee]"
            />
            <button
              onClick={() => lancerRecherche()}
              className="rounded-md bg-[#22d3ee] px-4 py-2 text-sm font-semibold text-[#0a0a0f] transition-opacity hover:opacity-90"
            >
              {loading ? "…" : "OK"}
            </button>
          </div>

          {/* Filtres par nature de carte */}
          <div className="flex flex-wrap gap-1.5 px-3 pb-2">
            {TYPES.map((t) => {
              const actif = types.includes(t.id);
              return (
                <button
                  key={t.id}
                  onClick={() => {
                    const next = actif ? types.filter((x) => x !== t.id) : [...types, t.id];
                    setTypes(next);
                    if (query.trim().length >= 2) lancerRecherche(query, next);
                  }}
                  className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
                    actif
                      ? "border-[#22d3ee] bg-[#22d3ee]/15 text-[#22d3ee]"
                      : "border-[#262633] text-[#8a8aa0] hover:text-[#e6e6ef]"
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
            {types.length > 0 && (
              <button
                onClick={() => {
                  setTypes([]);
                  if (query.trim().length >= 2) lancerRecherche(query, []);
                }}
                className="rounded-full border border-[#3a3a46] px-2.5 py-1 text-[11px] text-[#8a8aa0] hover:text-[#ff5a5a]"
              >
                ✕ Filtres
              </button>
            )}
          </div>

          <p className="px-3 pb-2 text-[11px] uppercase tracking-wider text-[#5a5a6a]">
            {titreResultats}
          </p>

          {/* Grille aérée : 3 colonnes, grand écart */}
          <div className="grid min-h-0 flex-1 grid-cols-3 content-start gap-3 overflow-y-auto px-3 pb-4">
            {results.map((card) => (
              <CardTile
                key={card.id}
                card={card}
                onAdd={(c) => ajouterCarte(c)}
                onSelect={(c) => setSelected(selected === c.id ? null : c.id)}
                onRelated={afficherCartesLiees}
                selected={selected === card.id}
              />
            ))}
            {results.length === 0 && !loading && (
              <p className="col-span-full mt-4 text-xs leading-relaxed text-[#8a8aa0]">
                Tapez un nom puis Entrée. Survolez une carte et cliquez sur <b>+</b> pour
                l&apos;ajouter, ou glissez-la vers une zone. Cliquez une carte pour voir ses
                cartes liées.
              </p>
            )}
          </div>
        </aside>

        {/* ---------------- Colonne centrale : zones ---------------- */}
        <main className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          <DeckZone titre="Main Deck" zone="main" max={60} />
          <DeckZone titre="Extra Deck" zone="extra" max={15} />
          <DeckZone titre="Side Deck" zone="side" max={15} />
        </main>

        {/* ---------------- Colonne droite : analyse ---------------- */}
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
        e.dataTransfer.dropEffect = "copy";
        setSurvol(true);
      }}
      onDragLeave={() => setSurvol(false)}
      onDrop={(e) => {
        // stopPropagation + lecture unique : un drop = une carte ajoutée.
        e.preventDefault();
        e.stopPropagation();
        setSurvol(false);
        const raw = e.dataTransfer.getData("card");
        e.dataTransfer.clearData();
        if (!raw) return;
        try {
          ajouterCarte(JSON.parse(raw) as Card, zone);
        } catch {
          /* données de drag invalides : on ignore */
        }
      }}
      className={`rounded-lg border bg-[#0d0d14] p-4 transition-colors ${
        survol ? "border-[#22d3ee]" : "border-[#262633]"
      }`}
    >
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-sm uppercase tracking-wider">{titre}</h2>
        <span className={`text-xs font-semibold ${total > max ? "text-[#ff5a5a]" : "text-[#8a8aa0]"}`}>
          {total} / {max}
        </span>
      </div>

      {/* Vignettes plus larges (90px) et bien espacées */}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(90px,1fr))] gap-3">
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
          <p className="col-span-full py-4 text-xs text-[#5a5a6a]">Glissez des cartes ici.</p>
        )}
      </div>
    </section>
  );
}