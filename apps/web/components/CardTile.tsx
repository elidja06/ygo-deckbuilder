// apps/web/components/CardTile.tsx
"use client";

import type { Card } from "@/lib/ygoApi";

interface Props {
  card: Card;
  /** Ajouter la carte (bouton +, ou drop). */
  onAdd?: (card: Card) => void;
  /** Retirer un exemplaire (zones de deck). */
  onRemove?: () => void;
  /** Sélectionner la carte (affiche le bouton « Cartes liées »). */
  onSelect?: (card: Card) => void;
  /** Afficher les cartes du même archétype. */
  onRelated?: (card: Card) => void;
  selected?: boolean;
  quantite?: number;
  /** Format compact pour les zones de deck. */
  compact?: boolean;
}

const FRAME_COULEUR: Record<string, string> = {
  normal: "#C9A227",
  effect: "#C26B3A",
  ritual: "#3D7FD1",
  fusion: "#8453C8",
  synchro: "#D6D6DE",
  xyz: "#3A3A46",
  link: "#2C72E0",
  spell: "#1AA37A",
  trap: "#C2477E",
  pendulum: "#28B59B",
};

const couleurCadre = (frame: string): string => {
  const cle = Object.keys(FRAME_COULEUR).find((k) => frame.includes(k));
  return cle ? FRAME_COULEUR[cle] : "#3A3A46";
};

const estMonstre = (frame: string): boolean =>
  !frame.includes("spell") && !frame.includes("trap");

export default function CardTile({
  card,
  onAdd,
  onRemove,
  onSelect,
  onRelated,
  selected = false,
  quantite,
  compact = false,
}: Props) {
  const couleur = couleurCadre(card.frameType);
  const monstre = estMonstre(card.frameType);
  const nonTraduite = card.langue === "en";

  return (
    <div className="flex flex-col gap-1">
      <div
        draggable
        onDragStart={(e) => {
          // Une seule carte transportée, pas de propagation vers les parents.
          e.stopPropagation();
          e.dataTransfer.effectAllowed = "copy";
          e.dataTransfer.setData("card", JSON.stringify(card));
        }}
        onClick={(e) => {
          e.stopPropagation();
          if (onRemove) onRemove();
          else if (onSelect) onSelect(card);
        }}
        title={card.nomFr}
        className="group relative aspect-[59/86] cursor-pointer overflow-hidden rounded-md transition-transform hover:-translate-y-1"
        style={{
          boxShadow: selected
            ? `0 0 0 2px #22d3ee, 0 0 14px -2px #22d3ee`
            : `0 0 0 1.5px ${couleur}66`,
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={card.imageLocale}
          alt={card.nomFr}
          loading="lazy"
          draggable={false}
          className="pointer-events-none h-full w-full object-cover"
        />

        <span
          className="pointer-events-none absolute inset-0 rounded-md opacity-0 transition-opacity group-hover:opacity-100"
          style={{ boxShadow: `0 0 16px -2px ${couleur}, inset 0 0 0 1.5px ${couleur}` }}
        />

        {/* Carte non traduite en français : vignette EN */}
        {nonTraduite && (
          <span
            className="absolute left-1 top-1 z-10 rounded bg-[#0a0a0f]/90 px-1 text-[9px] font-bold tracking-wide text-[#ffb020]"
            title="Carte non traduite en français"
          >
            EN
          </span>
        )}

        {card.banStatus !== "unlimited" && (
          <span
            className="absolute right-1 top-1 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-[#0a0a0f] text-[11px] font-bold"
            style={{
              color: card.banStatus === "banned" ? "#ff5a5a" : "#ffb020",
              boxShadow: "0 0 0 1px currentColor",
            }}
          >
            {card.banStatus === "banned" ? "0" : card.banStatus === "limited" ? "1" : "2"}
          </span>
        )}

        {quantite && quantite > 1 ? (
          <span className="absolute bottom-0 right-0 z-10 rounded-tl bg-black/85 px-1.5 text-[12px] font-bold text-[#22d3ee]">
            ×{quantite}
          </span>
        ) : null}

        {/* Bouton + : ajout explicite, un clic = un exemplaire */}
        {onAdd && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onAdd(card);
            }}
            title="Ajouter au deck"
            className="absolute bottom-1 right-1 z-20 flex h-7 w-7 items-center justify-center rounded-full bg-[#22d3ee] text-base font-bold leading-none text-[#0a0a0f] opacity-0 transition-opacity group-hover:opacity-100"
          >
            +
          </button>
        )}

        {!compact && (
          <div className="pointer-events-none absolute inset-0 z-[5] flex flex-col justify-end bg-gradient-to-t from-black/95 via-black/60 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
            <p className="truncate font-display text-[11px] text-[#e6e6ef]">{card.nomFr}</p>
            <p className="mt-0.5 truncate text-[10px] text-[#8a8aa0]">
              {monstre
                ? `N/R ${card.niveauRangLink ?? "—"}${card.attribut ? ` · ${card.attribut}` : ""}`
                : card.type}
            </p>
            {monstre && (
              <p className="text-[10px] font-semibold" style={{ color: couleur }}>
                ATK {card.atk ?? "?"}
                {card.def !== null ? ` / DEF ${card.def}` : ` / LIEN ${card.niveauRangLink ?? "?"}`}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Bouton « Cartes liées », visible sous la carte sélectionnée */}
      {selected && onRelated && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRelated(card);
          }}
          className="w-full rounded border border-[#22d3ee]/60 bg-[#22d3ee]/10 px-1 py-1 text-[10px] font-semibold uppercase tracking-wide text-[#22d3ee] transition-colors hover:bg-[#22d3ee]/20"
        >
          Cartes liées
        </button>
      )}
    </div>
  );
}