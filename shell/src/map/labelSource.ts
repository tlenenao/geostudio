// SPDX-License-Identifier: Apache-2.0
// Étiquettes de carte (SP-27 §3.3), source GeoJSON calculée côté client.
//
// Pourquoi pas `feature-state` : ["feature-state", …] est INTERDIT dans une
// propriété layout, et `text-field` est layout. Le validateur du style-spec —
// celui-là même qu'appelle map.addLayer — rend
// « "feature-state" data expressions are not supported with layout
// properties. », et Style.addLayer fait `if (this._validate(...)) return;` :
// la couche n'aurait jamais été posée, sans exception à attraper. On construit
// donc une source dont chaque entité porte une VRAIE propriété texte, et
// text-field vaut ["get", "label"] — data-driven sur une propriété réelle,
// que le validateur accepte.
//
// Réutilise tel quel le moteur CEL du popup (interpolatePopupTemplate, SP-24)
// — jamais renderPopupTemplate, qui sanitize en markdown : MapLibre affiche
// du texte brut, pas du HTML. Vocabulaire du gabarit : `${record.champ}`,
// l'unique convention du dépôt (cf. MapView.tsx:507-513, popupTemplate.test.ts).
import { interpolatePopupTemplate } from "./popupTemplate";

export type LabelSourceFeature = {
  id: string | number | undefined;
  properties: Record<string, unknown>;
  geometry: unknown;
};

export type LabelFeatureCollection = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    id?: string | number;
    properties: { label: string };
    geometry: unknown;
  }[];
};

// Plafond d'entités étiquetées par rafraîchissement. Au-delà, MapLibre en
// masque la quasi-totalité par collision de symboles (text-allow-overlap n'est
// pas posé) : les évaluer est un travail pur perdu, et le coût CEL est linéaire
// en nombre d'entités. Même intention que le plafond de 5000 lignes du chemin
// MVT du cœur (SP-24).
export const MAX_LABEL_FEATURES = 2000;

export function buildLabelFeatureCollection(
  features: LabelSourceFeature[],
  template: string,
  options: { pkColumn?: string; maxFeatures?: number } = {},
): LabelFeatureCollection {
  const { pkColumn, maxFeatures = MAX_LABEL_FEATURES } = options;
  const seen = new Set<string>();
  const out: LabelFeatureCollection["features"] = [];
  // Compteurs AGRÉGÉS : un console.warn par rafraîchissement, jamais un par
  // entité. Mesuré : une propriété absente LÈVE dans cel-js, et
  // evaluateExpression (builder/expr.ts:12-18) journalise — sur une couche où
  // seules certaines entités portent le champ, c'est un flot d'avertissements.
  let failed = 0;
  let truncated = 0;
  for (const f of features) {
    if (f.geometry == null) continue;
    // querySourceFeatures renvoie un morceau par tuile : dédupliquer, sinon
    // une entité à cheval sur quatre tuiles reçoit quatre étiquettes.
    //
    // CONSÉQUENCE ASSUMÉE (constat N8, Mineur) : on garde le PREMIER fragment
    // rencontré, donc une géométrie CLIPPÉE à la tuile —
    // `Tile.querySourceFeatures` construit un GeoJSONFeature par entité de
    // tuile et sa géométrie vaut `toGeoJSON(x, y, z).geometry` (lng/lat, bonne
    // nouvelle, mais clippé). `symbol-placement` valant "point" par défaut,
    // MapLibre ancre l'étiquette sur ce fragment : sur une grande commune à
    // cheval sur quatre tuiles, l'étiquette peut être nettement décentrée et
    // SAUTER d'un rafraîchissement à l'autre selon l'ordre de
    // getRenderableIds(). Recoller les fragments demanderait une union
    // géométrique côté client : hors périmètre, consigné dans les suivis.
    const key =
      f.id != null
        ? `id:${f.id}`
        : pkColumn && f.properties[pkColumn] != null
          ? `pk:${String(f.properties[pkColumn])}`
          : `props:${JSON.stringify(f.properties)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (out.length >= maxFeatures) {
      truncated += 1;
      continue;
    }
    let label: string;
    try {
      label = interpolatePopupTemplate(template, {
        vars: {},
        user: { name: "" },
        record: f.properties,
      });
    } catch {
      // interpolatePopupTemplate ne devrait pas lever (evaluateExpression
      // avale déjà), mais une entité ne doit jamais faire tomber la passe.
      failed += 1;
      continue;
    }
    // Une étiquette vide ne produirait qu'un halo invisible : ne pas la poser.
    if (label.trim() === "") {
      failed += 1;
      continue;
    }
    out.push({
      type: "Feature",
      ...(f.id != null ? { id: f.id } : {}),
      properties: { label },
      geometry: f.geometry,
    });
  }
  if (truncated > 0) {
    console.warn(
      `labelSource: ${maxFeatures} étiquettes au maximum, ${truncated} entités ignorées ` +
        `— resserrez l'emprise ou filtrez la couche.`,
    );
  }
  if (failed > 0) {
    console.warn(
      `labelSource: ${failed} entités sans étiquette exploitable (gabarit « ${template} »).`,
    );
  }
  return { type: "FeatureCollection", features: out };
}
