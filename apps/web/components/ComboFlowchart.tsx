// apps/web/components/ComboFlowchart.tsx
"use client";

import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import type { Combo, ComboStep } from "@/lib/ygoApi";

// Libellés FR lisibles pour le type d'action de chaque étape.
const ACTION_LABEL: Record<string, string> = {
  invocation_normale: "Invocation Normale",
  invocation_speciale: "Invocation Spéciale",
  activation_effet: "Activation d'effet",
  tuto: "Recherche / Tuto",
  invocation_link: "Invocation Link",
  invocation_xyz: "Invocation Xyz",
  invocation_synchro: "Invocation Synchro",
};

// ---------- Nœud personnalisé : une étape de combo ----------

type StepData = { step: ComboStep; index: number };

function StepNode({ data }: NodeProps<StepData>) {
  const { step, index } = data;
  return (
    <div className="w-60 rounded-lg border border-neutral-700 bg-neutral-900 p-3 text-neutral-100 shadow-lg">
      <Handle type="target" position={Position.Top} className="!bg-indigo-500" />
      <div className="mb-1 flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-bold">
          {index}
        </span>
        <span className="text-xs font-semibold uppercase tracking-wide text-indigo-300">
          {ACTION_LABEL[step.action] ?? step.action}
        </span>
      </div>
      <p className="text-sm leading-snug">{step.explicationFr}</p>
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-500" />
    </div>
  );
}

const nodeTypes = { step: StepNode };

// ---------- Mise en page de l'arbre ----------
// Disposition simple en niveaux (BFS depuis la racine). Pour des arbres larges,
// brancher dagre/elk ; ici on reste léger et déterministe.

function layout(steps: ComboStep[]): { nodes: Node[]; edges: Edge[] } {
  const enfants = new Map<string | null, ComboStep[]>();
  steps.forEach((s) => {
    const arr = enfants.get(s.parentId) ?? [];
    arr.push(s);
    enfants.set(s.parentId, arr);
  });

  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const X = 290; // espacement horizontal entre frères
  const Y = 150; // espacement vertical entre niveaux
  let compteur = 1;

  const placer = (parentId: string | null, niveau: number, offsetX: number) => {
    const frateries = enfants.get(parentId) ?? [];
    const largeur = (frateries.length - 1) * X;
    frateries.forEach((step, i) => {
      const x = offsetX + i * X - largeur / 2;
      nodes.push({
        id: step.id,
        type: "step",
        position: { x, y: niveau * Y },
        data: { step, index: compteur++ },
      });
      if (step.parentId) {
        edges.push({
          id: `${step.parentId}-${step.id}`,
          source: step.parentId,
          target: step.id,
          animated: true,
          style: { stroke: "#6366f1" },
        });
      }
      placer(step.id, niveau + 1, x);
    });
  };

  placer(null, 0, 0);
  return { nodes, edges };
}

// ---------- Composant exporté ----------

export default function ComboFlowchart({ combo }: { combo: Combo }) {
  const { nodes, edges } = useMemo(() => layout(combo.steps), [combo.steps]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <h3 className="text-base font-semibold">{combo.nom}</h3>
        <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300">
          {combo.cartesRequises} carte{combo.cartesRequises > 1 ? "s" : ""} requise{combo.cartesRequises > 1 ? "s" : ""}
        </span>
        {!combo.realisable && (
          <span className="rounded-full bg-amber-600/20 px-2 py-0.5 text-xs text-amber-300">
            Cartes manquantes dans le deck
          </span>
        )}
      </div>

      <div className="h-[460px] w-full rounded-lg border border-neutral-800 bg-neutral-950">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} color="#27272a" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      {combo.resultat && (
        <p className="text-sm text-neutral-400">
          <span className="font-medium text-neutral-200">Board visé :</span> {combo.resultat}
        </p>
      )}
    </div>
  );
}
