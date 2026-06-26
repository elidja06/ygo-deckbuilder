// apps/web/components/CardTile.tsx
"use client";

import type { Card } from "@/lib/ygoApi";

interface Props {
  card: Card;
  onAdd?: (card: Card) => void;   // recherche : drag + double-clic
  onRemove?: () => void;          // zone de deck : clic = retirer
  quantite?: number;
  compact?: boolean;
}

// Couleur du cadre selon le frameType (codes Yu-Gi-Oh!).
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

export default function CardTile({ card, onAdd, onRemove, quantite, compact = false }: Props) {
  const couleur = couleurCadre(card.frameType);
  const monstre = estMonstre(card.frameType);

  return (
    <div
      draggable={!!onAdd}
      onDragStart={
        onAdd ? (e) => e.dataTransfer.setData("card", JSON.stringify(card)) : undefined
      }
      onDoubleClick={onAdd ? () => onAdd(card) : undefined}
      onClick={onRemove}
      title={card.nomFr}
      className="group relative aspect-[59/86] cursor-pointer overflow-hidden rounded-md transition-transform hover:-translate-y-0.5"
      style={{ boxShadow: `0 0 0 1.5px ${couleur}55` }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={card.imageLocale}
        alt={card.nomFr}
        loading="lazy"
        onError={(e) => {
          (e.currentTarget as HTMLImageElement).style.opacity = "0";
        }}
        className="h-full w-full object-cover"
      />

      {/* Liseré lumineux au survol (couleur du cadre) */}
      <span
        className="pointer-events-none absolute inset-0 rounded-md opacity-0 transition-opacity group-hover:opacity-100"
        style={{ boxShadow: `0 0 16px -2px ${couleur}, inset 0 0 0 1.5px ${couleur}` }}
      />

      {/* Badge banlist */}
      {card.banStatus !== "unlimited" && (
        <span
          className="absolute right-1 top-1 z-10 flex h-4 w-4 items-center justify-center rounded-full bg-[#0a0a0f] text-[10px] font-bold"
          style={{
            color: card.banStatus === "banned" ? "#ff5a5a" : "#ffb020",
            boxShadow: "0 0 0 1px currentColor",
          }}
        >
          {card.banStatus === "banned" ? "0" : card.banStatus === "limited" ? "1" : "2"}
        </span>
      )}

      {/* Quantité (zones de deck) */}
      {quantite && quantite > 1 ? (
        <span className="absolute bottom-0 right-0 z-10 bg-black/85 px-1 text-[11px] font-bold text-[#22d3ee]">
          ×{quantite}
        </span>
      ) : null}

      {/* Détail au survol (recherche uniquement) */}
      {!compact && (
        <div className="absolute inset-0 z-[5] flex flex-col justify-end bg-gradient-to-t from-black/95 via-black/70 to-transparent p-1.5 opacity-0 transition-opacity group-hover:opacity-100">
          <p className="truncate font-display text-[10px] text-[#e6e6ef]">{card.nomFr}</p>
          <p className="mt-0.5 truncate text-[9px] text-[#8a8aa0]">
            {monstre
              ? `N/R ${card.niveauRangLink ?? "—"}${card.attribut ? ` · ${card.attribut}` : ""}`
              : card.type}
          </p>
          {monstre && (
            <p className="text-[9px] font-semibold" style={{ color: couleur }}>
              ATK {card.atk ?? "?"}
              {card.def !== null ? ` / DEF ${card.def}` : ` / LIEN ${card.niveauRangLink ?? "?"}`}
            </p>
          )}
          <p className="mt-1 max-h-[3.2rem] overflow-hidden text-[8px] leading-snug text-[#b9b9cc]">
            {card.effetFr}
          </p>
        </div>
      )}
    </div>
  );
}
