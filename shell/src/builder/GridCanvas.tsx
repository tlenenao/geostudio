// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import type { WidgetItem } from "../api/types";
import { t } from "../i18n";
import { getWidget } from "./registry";
import { GRID_COLS, positionsFor, styleForPos, type Breakpoint } from "./grid";

// Commandes d'un widget sélectionné : 24 px minimum (WCAG 2.5.8), 44 px sur
// pointeur grossier (P31.07).
const CTL =
  "min-h-6 min-w-6 px-1 text-xs text-surface pointer-coarse:min-h-11 pointer-coarse:min-w-11";

export function GridCanvas({
  items,
  breakpoint,
  editable,
  selectedId,
  onSelect,
  onMoveItem,
  onRemoveItem,
  onResizeItem,
  onDuplicateItem,
  renderItem,
}: {
  items: WidgetItem[];
  breakpoint: Breakpoint;
  editable: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMoveItem: (id: string, dxCells: number, dyCells: number) => void;
  onRemoveItem: (id: string) => void;
  onResizeItem?: (id: string, dwCells: number, dhCells: number) => void;
  onDuplicateItem?: (id: string) => void;
  renderItem: (item: WidgetItem) => ReactNode;
}) {
  const positions = positionsFor(items, breakpoint);
  // Nom accessible = libellé du type de widget (« Table »), numéroté quand
  // plusieurs widgets du même type cohabitent (jamais l'identifiant technique).
  const labelOf = (item: WidgetItem) => getWidget(item.widget)?.label ?? item.widget;
  const nameOf = (item: WidgetItem) => {
    const label = labelOf(item);
    const same = items.filter((i) => labelOf(i) === label);
    return same.length > 1 ? `${label} ${same.indexOf(item) + 1}` : label;
  };
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
        const pos = positions.get(item.id)!;
        const selected = editable && item.id === selectedId;
        return (
          <div
            key={item.id}
            data-col={pos.x}
            data-row={pos.y}
            style={styleForPos(pos)}
            className={`relative rounded ${selected ? "outline outline-2 outline-blue-500" : ""}`}
          >
            {editable && (
              <button
                type="button"
                aria-label={t("gridCanvas.select", { name: nameOf(item) })}
                className="absolute inset-0 z-10 cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(item.id);
                }}
              />
            )}
            <div
              className={`h-full w-full overflow-hidden rounded p-1 ${editable ? "pointer-events-none" : ""}`}
            >
              {renderItem(item)}
            </div>
            {/* Commandes hors du clipping du widget (seul son contenu est
                overflow-hidden), sous la cellule et avec retour à la ligne, pour
                que les 24/44 px ne soient ni rognés ni masqués par la hauteur de
                ligne de 40 px (P31.07). */}
            {selected && (
              <div className="absolute right-0 top-full z-30 flex w-max max-w-[min(24rem,90vw)] flex-wrap justify-end gap-0.5 rounded bg-surface p-0.5 shadow-md">
                <button
                  type="button"
                  aria-label={t("gridCanvas.moveLeft", { name: nameOf(item) })}
                  className={`bg-accent ${CTL}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onMoveItem(item.id, -1, 0);
                  }}
                >
                  ←
                </button>
                <button
                  type="button"
                  aria-label={t("gridCanvas.moveRight", { name: nameOf(item) })}
                  className={`bg-accent ${CTL}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onMoveItem(item.id, 1, 0);
                  }}
                >
                  →
                </button>
                <button
                  type="button"
                  aria-label={t("gridCanvas.moveDown", { name: nameOf(item) })}
                  className={`bg-accent ${CTL}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onMoveItem(item.id, 0, 1);
                  }}
                >
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={t("gridCanvas.moveUp", { name: nameOf(item) })}
                  className={`bg-accent ${CTL}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onMoveItem(item.id, 0, -1);
                  }}
                >
                  ↑
                </button>
                {onResizeItem && (
                  <>
                    <button
                      type="button"
                      aria-label={t("gridCanvas.widen", { name: nameOf(item) })}
                      className={`bg-accent ${CTL}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onResizeItem(item.id, 1, 0);
                      }}
                    >
                      ↔+
                    </button>
                    <button
                      type="button"
                      aria-label={t("gridCanvas.narrow", { name: nameOf(item) })}
                      className={`bg-accent ${CTL}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onResizeItem(item.id, -1, 0);
                      }}
                    >
                      ↔−
                    </button>
                    <button
                      type="button"
                      aria-label={t("gridCanvas.taller", { name: nameOf(item) })}
                      className={`bg-accent ${CTL}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onResizeItem(item.id, 0, 1);
                      }}
                    >
                      ↕+
                    </button>
                    <button
                      type="button"
                      aria-label={t("gridCanvas.shorter", { name: nameOf(item) })}
                      className={`bg-accent ${CTL}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onResizeItem(item.id, 0, -1);
                      }}
                    >
                      ↕−
                    </button>
                  </>
                )}
                {onDuplicateItem && (
                  <button
                    type="button"
                    aria-label={t("gridCanvas.duplicate", { name: nameOf(item) })}
                    className={`bg-accent ${CTL}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDuplicateItem(item.id);
                    }}
                  >
                    ⧉
                  </button>
                )}
                <button
                  type="button"
                  aria-label={t("gridCanvas.remove", { name: nameOf(item) })}
                  className={`bg-danger ${CTL}`}
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
