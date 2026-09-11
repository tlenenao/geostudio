// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import type { WidgetItem } from "../api/types";
import { GRID_COLS, posFor, styleForPos, type Breakpoint } from "./grid";

export function GridCanvas({
  items,
  breakpoint,
  editable,
  selectedId,
  onSelect,
  onMoveItem,
  onRemoveItem,
  renderItem,
}: {
  items: WidgetItem[];
  breakpoint: Breakpoint;
  editable: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMoveItem: (id: string, dxCells: number, dyCells: number) => void;
  onRemoveItem: (id: string) => void;
  renderItem: (item: WidgetItem) => ReactNode;
}) {
  return (
    <div
      className="grid h-full w-full gap-1 bg-[var(--gs-color-surface)]"
      data-breakpoint={breakpoint}
      style={{ gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`, gridAutoRows: "40px" }}
      // role="presentation" : ce conteneur de mise en page ne porte aucune
      // sémantique propre — les vraies commandes (sélectionner/déplacer/
      // supprimer un widget) sont les <button> réels rendus ci-dessous,
      // déjà accessibles au clavier. Le clic sur la zone vide ne fait que
      // désélectionner, une commodité qui n'a aujourd'hui aucun équivalent
      // clavier dédié (limitation connue, pas corrigée ici — aucune action
      // n'est pour autant rendue inatteignable : sélectionner un autre
      // widget, ou le supprimer via Suppr/Retour arrière déjà câblé au
      // niveau de la page, restent possibles sans jamais utiliser cette
      // zone). Annoter le rôle plutôt que masquer la règle
      // jsx-a11y/no-static-element-interactions.
      role="presentation"
      onClick={() => editable && onSelect(null)}
    >
      {items.map((item) => {
        const pos = posFor(item, breakpoint);
        const selected = editable && item.id === selectedId;
        return (
          <div
            key={item.id}
            data-col={pos.x}
            data-row={pos.y}
            style={styleForPos(pos)}
            className={`relative overflow-hidden rounded ${selected ? "outline outline-2 outline-blue-500" : ""}`}
          >
            {editable && (
              <button
                type="button"
                aria-label={`Sélectionner widget-${item.id}`}
                className="absolute inset-0 z-10 cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(item.id);
                }}
              />
            )}
            <div className={`h-full w-full p-1 ${editable ? "pointer-events-none" : ""}`}>
              {renderItem(item)}
            </div>
            {selected && (
              <div className="absolute right-0 top-0 z-20 flex gap-0.5">
                <button
                  type="button"
                  aria-label={`Déplacer widget-${item.id} à gauche`}
                  className="bg-blue-500 px-1 text-xs text-white"
                  onClick={(e) => {
                    e.stopPropagation();
                    onMoveItem(item.id, -1, 0);
                  }}
                >
                  ←
                </button>
                <button
                  type="button"
                  aria-label={`Déplacer widget-${item.id} à droite`}
                  className="bg-blue-500 px-1 text-xs text-white"
                  onClick={(e) => {
                    e.stopPropagation();
                    onMoveItem(item.id, 1, 0);
                  }}
                >
                  →
                </button>
                <button
                  type="button"
                  aria-label={`Déplacer widget-${item.id} en bas`}
                  className="bg-blue-500 px-1 text-xs text-white"
                  onClick={(e) => {
                    e.stopPropagation();
                    onMoveItem(item.id, 0, 1);
                  }}
                >
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={`Déplacer widget-${item.id} en haut`}
                  className="bg-blue-500 px-1 text-xs text-white"
                  onClick={(e) => {
                    e.stopPropagation();
                    onMoveItem(item.id, 0, -1);
                  }}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={`Supprimer widget-${item.id}`}
                  className="bg-red-600 px-1 text-xs text-white"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveItem(item.id);
                  }}
                >
                  ✕
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
