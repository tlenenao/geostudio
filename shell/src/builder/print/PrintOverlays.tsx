// SPDX-License-Identifier: Apache-2.0
// ARC-16 : éléments de la feuille d'impression (mode `exportRender`),
// partagés par MapEditorPage et AppRuntimePage. L'échelle graphique n'en fait
// pas partie : c'est un contrôle MapLibre (MapView `showScaleBar`).
// Disposition : titre en haut à gauche ; logo + flèche du nord en haut à
// droite ; échelle en bas à gauche ; légende + cartouche en bas à droite ;
// texte libre centré en bas.
import type { ReactNode } from "react";
import type { PrintLayoutConfig } from "../../api/types";
import { t } from "../../i18n";
import "../../i18n/domains/widgets";

// gs-raw-color-ok-begin: la feuille imprimée reste claire quelle que soit l'ambiance (aspect papier, spec §2.2) — pas un style d'UI
const PAPER = "rounded bg-white/90 px-2 py-1 text-black";
// gs-raw-color-ok-end

// Liste des couches visibles (entêtes de légende), même aspect papier.
export function PrintLayerTitles({ titles }: { titles: { id: string; title: string }[] }) {
  return (
    <ul className={`text-xs ${PAPER}`}>
      {titles.map((l) => (
        <li key={l.id}>{l.title}</li>
      ))}
    </ul>
  );
}

export function PrintOverlays({
  layout,
  legend,
}: {
  layout: PrintLayoutConfig | null | undefined;
  // Contenu de la légende (déjà filtré par l'appelant) ; rendu seulement si
  // `showLegend` est vrai.
  legend?: ReactNode;
}) {
  if (!layout) return null;
  const showLegend = layout.showLegend && legend;
  return (
    <>
      {layout.title && (
        <div
          data-testid="print-title"
          className={`absolute left-2 top-2 text-sm font-medium ${PAPER}`}
        >
          {layout.title}
        </div>
      )}
      {(layout.logo || layout.northArrow) && (
        <div className="absolute right-2 top-2 flex flex-col items-end gap-2">
          {layout.logo && (
            <img
              data-testid="print-logo"
              src={layout.logo}
              alt={t("printOverlay.logoAlt")}
              className={`max-h-16 max-w-40 object-contain ${PAPER}`}
            />
          )}
          {layout.northArrow && (
            <svg
              data-testid="print-north-arrow"
              role="img"
              aria-label={t("printOverlay.northArrowAria")}
              viewBox="0 0 40 56"
              width="40"
              height="56"
              className={PAPER}
            >
              <polygon points="20,4 32,40 20,32 8,40" fill="currentColor" />
              <text x="20" y="54" textAnchor="middle" fontSize="14" fill="currentColor">
                N
              </text>
            </svg>
          )}
        </div>
      )}
      {(showLegend || layout.cartouche) && (
        <div className="absolute bottom-2 right-2 flex flex-col items-end gap-2">
          {showLegend && (
            <div data-testid="print-legend" className="flex flex-col items-end gap-2">
              {legend}
            </div>
          )}
          {layout.cartouche && (
            <div data-testid="print-cartouche" className={`text-xs ${PAPER}`}>
              {layout.cartouche}
            </div>
          )}
        </div>
      )}
      {layout.freeText && (
        <p
          data-testid="print-free-text"
          className={`absolute bottom-2 left-1/2 max-w-[40%] -translate-x-1/2 whitespace-pre-line text-xs ${PAPER}`}
        >
          {layout.freeText}
        </p>
      )}
    </>
  );
}
