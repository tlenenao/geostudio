// SPDX-License-Identifier: Apache-2.0
// ARC-16 : légendes de symbologie de toutes les couches vecteur visibles,
// partagées par le panneau d'aperçu de l'éditeur et la feuille d'impression
// (la légende imprimée reflète ainsi la symbologie courante, 4 modes avancés
// compris, sans second moteur).
import type { MapLayer } from "../api/types";
import {
  buildLegend,
  paintExtrasOf,
  symbologyToPaintInputs,
} from "../builder/widgets/mapSymbology";
import { MapSymbologyLegend } from "./MapSymbologyLegend";

export function LayerSymbologyLegends({ layers }: { layers: MapLayer[] }) {
  return (
    <>
      {layers
        .filter((l): l is Extract<MapLayer, { kind: "vector" }> => l.kind === "vector" && l.visible)
        .map((l) => {
          if (!l.symbology) return null;
          const { encodings, colorDomain, sizeDomain, palette, stroke } = symbologyToPaintInputs(
            l.symbology,
            undefined,
          );
          const legend = buildLegend(
            encodings,
            colorDomain,
            sizeDomain,
            l.geometryKind ?? "polygon",
            palette,
            paintExtrasOf(l.symbology, stroke),
          );
          return legend ? <MapSymbologyLegend key={l.id} legend={legend} variant="static" /> : null;
        })}
    </>
  );
}
