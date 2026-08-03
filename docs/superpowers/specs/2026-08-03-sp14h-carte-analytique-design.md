# SP-14h — Carte analytique : symbologie pilotée par dataset (design)

> **Date : 2026-08-03 · Statut : validé (brainstorm)**
> Huitième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités**, **SP-14e — KPI riche &
> séries temporelles comparées**, **SP-14f — Nouveaux types de graphiques**
> et **SP-14g — Tableau croisé / pivot**. Traite le deuxième des éléments
> encore listés « hors périmètre » par 14g (« Carte analytique, conteneurs
> [...], requête visuelle, SQL Lab, source `arcgis`, MCP analytique —
> sous-parties SP-14 ultérieures (14h…) ») : la **carte analytique**
> (« MapConfig complet + symbologie pilotée par dataset via les mêmes
> `encodings` que les charts »). Conteneurs (onglets/modale/tiroir), requête
> visuelle, SQL Lab, source `arcgis`, MCP analytique restent hors périmètre —
> sous-parties SP-14 ultérieures (14i…).

## 1. Objectif & non-buts

**Objectif.** Le widget `map` existant (`shell/src/builder/widgets/mapWidget.tsx`
— une seule couche issue d'une seule `DataSource` de type `features`, sans
aucun style configurable) gagne une symbologie pilotée par les données :
`encodings.color` (catégoriel ou numérique) et `encodings.size` (numérique,
cercles proportionnels sur géométrie ponctuelle), éditables dans son
`PropsPanel`, avec légende — la question type étant « colorer les communes
par région, ou dimensionner les points d'incident par montant de dégâts »,
sans configuration MapLibre manuelle.

**Constat clé qui cadre l'approche.** Le widget `map` construit déjà son
`MapConfig` entièrement côté client (`mapWidget.tsx:51-57`) à partir d'une
seule `DataSource` `features` ; son unique couche est toujours rendue en
`type: "fill"`, codé en dur dans le fichier partagé `MapView.tsx:58`, quelle
que soit la géométrie réelle (un jeu de données ponctuel ou linéaire y est
donc actuellement invisible — bug latent préexistant, non introduit par ce
plan mais corrigé comme effet de bord nécessaire à la taille proportionnelle).
Le calcul du domaine d'un encoding (bornes numériques, valeurs distinctes)
suit exactement le patron déjà utilisé par `sliderFilter.tsx` (requête
`statistics` avec `measures: [{field, agg:"min"}, {field, agg:"max"}]`,
`sliderFilter.tsx:39-49`) et `selectFilter.tsx` (`statistics` avec
`groupBy: field`, `selectFilter.tsx:39-49`) — zéro nouveau mécanisme côté
`core`, zéro changement à `itemClient.ts`/`DataSourcePanel.tsx`.

**Non-buts explicites** (reportés) :

- **MapConfig multi-couches / basemap éditable dans le widget** — le widget
  garde une seule couche issue d'une seule `DataSource`, comme aujourd'hui ;
  l'édition multi-couches/basemap reste le rôle de l'éditeur de carte complet
  (`MapEditorPage.tsx`). Le « MapConfig complet » de la feuille de route n'est
  donc couvert que pour sa partie symbologie dans ce plan.
- **Choroplèthe par jointure agrégat↔géométrie** (couleur = valeur agrégée
  d'une autre requête sur des zones, ex. « nombre d'incidents par commune »
  affiché sur les polygones communes) — v1 encode uniquement un attribut brut
  porté par l'entité elle-même (`DataRecord.properties`), jamais une valeur
  jointe depuis un `groupBy` séparé. Rester sur `features` uniquement.
- **Palette personnalisable, classes par quantile/Jenks** — v1 : une palette
  qualitative fixe (~8 couleurs, cycle au-delà) pour le catégoriel, une rampe
  séquentielle fixe à 2 arrêts pour le numérique, interpolation linéaire
  continue. Pas de sélecteur de couleurs, pas de nombre de classes
  configurable.
- **Encoding de forme/icône, multi-champs combinés (ex. couleur ET forme sur
  le même champ)** — seuls `color` et `size` existent, un champ chacun.
- **Réception de cross-filter sans refetch (« highlight » pur)** — hors
  périmètre : le widget reçoit déjà le cross-filter par narrowing de requête
  (le patch `derivePatch` s'applique à sa `DataSource` comme à tout widget,
  `DataContext.tsx:49-52`, inchangé) ; aucune surbrillance additionnelle n'est
  ajoutée.
- Conteneurs (onglets/modale/tiroir), requête visuelle, SQL Lab, source
  `arcgis`, MCP analytique — reste de la liste « widgets analytiques » /
  périmètre SP-14, sous-parties ultérieures.
- Bookmarks/situations nommées, cross-filter inter-datasets — toujours hors
  périmètre (inchangé depuis 14b).

Le modèle reste additif et à faible surface partagée : un champ optionnel
ajouté à `MapLayer` (rétrocompatible, cf. §3), une branche supplémentaire
dans `MapView.applyLayers` honorant ce champ, et le reste du travail contenu
dans `mapWidget.tsx` + un nouveau module `mapSymbology.ts`. Aucun changement à
`core/`, `itemClient.ts`, `DataSourcePanel.tsx`, `LayersPanel.tsx`,
`MapEditorPage.tsx` ou `MapLegend.tsx`.

## 2. Props & calcul du domaine

```ts
type MapWidgetProps = {
  dataSourceId?: string;
  encodings?: {
    color?: { field: string; mode: "categorical" | "numeric" };
    size?: { field: string }; // toujours numérique
  };
};
```

**`PropsPanel`** — sous le `DataSourceSelect` existant (`mapWidget.tsx:35-36`,
inchangé) : un bloc « Couleur » (champ texte + `<select>` catégoriel/numérique,
patron identique aux champs texte de `sliderFilter.tsx:19-22`) et un bloc
« Taille » (champ texte seul, toujours numérique — pas de sélecteur de mode).
Les deux blocs sont optionnels ; laisser un champ vide désactive l'encoding
correspondant (couche rendue sans style, comportement actuel inchangé).

**Domaine** — deux requêtes `statistics` supplémentaires, indépendantes de la
`DataSource` `features` qui alimente la géométrie/les attributs affichés (même
séparation que `sliderFilter`/`selectFilter`, qui interrogent aussi
`statistics` en plus de la source réelle du widget qu'ils filtrent) :

```ts
// couleur catégorielle
client.queryDataSource({ type: "statistics", datasetId, query: { groupBy: field } });
// → valeurs distinctes (r.id), assignées dans l'ordre à la palette qualitative fixe

// couleur/taille numérique
client.queryDataSource({ type: "statistics", datasetId,
  query: { measures: [{ field, agg: "min" }, { field, agg: "max" }] } });
// → { min, max } depuis properties[0], comme sliderFilter.tsx:44-47
```

Ces requêtes ne partent que si `ctx.data?.datasetId` est présent (la
`DataSource` `features` doit être liée à un dataset — même contrainte que les
filtres existants) ; sinon l'encoding est ignoré silencieusement, couche
rendue sans style, aucun message d'erreur bloquant (dégradation ordinaire,
pas un état d'erreur).

## 3. Rendu — `MapLayer.renderAs` (champ additif) & `mapSymbology.ts`

`shell/src/api/types.ts:62` — le variant `feature` de `MapLayer` gagne un
champ optionnel :

```ts
| { id: string; title: string; visible: boolean; kind: "feature"; url: string;
    paint?: Record<string, unknown>; renderAs?: "fill" | "circle" | "line" }
```

Absent ⇒ comportement actuel inchangé (`"fill"`, valeur implicite) : zéro
impact sur les `MapConfig` déjà enregistrés (éditeur de carte complet,
`MapEditorPage.tsx`) qui ne renseignent jamais ce champ.

`shell/src/map/MapView.tsx:56-58` (`applyLayers`, cas `kind === "feature"`) —
lit `layer.renderAs` pour choisir le type MapLibre au lieu de `"fill"` codé en
dur :

```ts
} else if (layer.kind === "feature") {
  const type = layer.renderAs ?? "fill";
  map.addSource(layer.id, { type: "geojson", data: layer.url });
  map.addLayer({ id: layer.id, type, source: layer.id, paint: layer.paint ?? {} });
  // ... handler de clic inchangé
```

Seul changement dans ce fichier partagé.

**Nouveau module** `shell/src/builder/widgets/mapSymbology.ts` (même esprit
que `chartOption.ts` : fonctions pures, testables sans rendu) :

```ts
type ColorDomain = { kind: "categorical"; values: string[] } | { kind: "numeric"; min: number; max: number };
type SizeDomain = { min: number; max: number };
type GeometryKind = "point" | "line" | "polygon";

function detectGeometryKind(geometry: unknown): GeometryKind; // Point/MultiPoint→point, Line*→line, Polygon*→polygon
function buildMapPaint(
  encodings: MapWidgetProps["encodings"],
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
): { renderAs: "fill" | "circle" | "line"; paint: Record<string, unknown> };
function buildLegend(encodings, colorDomain, sizeDomain): LegendSpec | null;
```

`buildMapPaint` :
- `renderAs` = `"circle"` si `geometryKind === "point"`, sinon `"line"` si
  `"line"`, sinon `"fill"` (polygone) — indépendant des encodings actifs.
- Propriété de couleur ciblée = `circle-color`/`line-color`/`fill-color`
  selon `renderAs`. Catégoriel → expression MapLibre `["match", ["get", field],
  v1, c1, v2, c2, ..., defaultColor]`. Numérique → `["interpolate", ["linear"],
  ["get", field], min, colorLow, max, colorHigh]` (si `min === max`, couleur
  constante `colorLow`, pas de division par zéro dans l'expression MapLibre).
- Taille → seulement si `renderAs === "circle"` (géométrie ponctuelle) :
  `circle-radius` = `["interpolate", ["linear"], ["get", field], min, 4, max, 24]`
  (bornes constantes si `min === max`, même garde). Ignorée pour toute autre
  géométrie — pas d'erreur, juste pas de `circle-radius` dans le paint.
- Aucun encoding actif ⇒ `paint: {}` (comportement actuel).

`mapWidget.tsx` détecte `geometryKind` depuis `ctx.data.records[0]?.geometry`
(présent uniquement pour les `DataSource` `features`, `DataRecord.geometry`,
`types.ts:316`), appelle `buildMapPaint`/`buildLegend`, injecte le résultat
dans la couche unique du `MapConfig` construit (`mapWidget.tsx:51-57`,
`renderAs`/`paint` ajoutés à l'objet couche existant).

**Légende** — overlay possédé par `mapWidget.tsx` (pas le `MapLegend` partagé
utilisé par `MapView`, qui reste générique liste-de-titres pour l'éditeur de
carte, `MapLegend.tsx` inchangé) : positionné en superposition absolue
(complémentaire du `MapLegend` déjà rendu par `MapView`, aucun conflit de
zone — coins opposés). Rendu conditionnel à `buildLegend(...) !== null` :
- Catégoriel : liste de swatches couleur + libellé de valeur.
- Numérique (couleur) : barre de dégradé + bornes min/max affichées.
- Taille : 2-3 cercles d'échantillon avec leur valeur associée.

Le clic sur une entité déclenche toujours `setCrossFilter` par pk
(`mapWidget.tsx:69-74`, inchangé) — indépendant des encodings.

## 4. Tests

**Unit (Vitest)** — `mapSymbology.test.ts` :
- `detectGeometryKind` — `Point`/`MultiPoint` → `"point"`,
  `LineString`/`MultiLineString` → `"line"`, `Polygon`/`MultiPolygon` →
  `"polygon"`.
- `buildMapPaint` — expression `match` correcte pour N valeurs catégorielles
  avec couleur par défaut en dernier argument ; cycle de palette au-delà de 8
  valeurs distinctes (9ᵉ valeur réutilise la 1ʳᵉ couleur) ; expression
  `interpolate` correcte pour un domaine numérique ; `min === max` → couleur
  et taille constantes, pas de division par zéro ; `renderAs` correct pour
  chacune des 3 géométries ; `circle-radius` absent du paint si
  `geometryKind !== "point"` même si `encodings.size` est configuré.
- `buildLegend` — `null` si aucun encoding actif ; structure correcte pour
  chaque combinaison catégoriel/numérique/taille.

`mapWidget.test.tsx` : `PropsPanel` affiche les champs couleur (texte + mode)
et taille ; couche construite avec `renderAs`/`paint` corrects quand
`ctx.data` porte des enregistrements avec géométrie et que `encodings` est
configuré ; couche `paint: {}`/`renderAs` absent quand aucun encoding n'est
configuré (régression du comportement actuel) ; clic sur une entité stylée
appelle toujours `setCrossFilter` avec le même contrat qu'avant (pk,
inchangé).

**E2E (Playwright)** — étend `shell/e2e/analytics-context.spec.ts` :
1. Widget `map` avec `encodings.color` catégoriel sur un dataset polygonal →
   légende avec swatches, présence visuelle de plusieurs couleurs distinctes
   sur la carte (vérifié via les propriétés `paint` de la couche MapLibre,
   pas seulement le rendu visuel).
2. Widget `map` avec `encodings.color` + `encodings.size` numériques sur un
   dataset ponctuel → couche rendue en `circle`, légende dégradé + tailles
   échantillon affichée.
3. Clic sur une entité stylée → cross-filter toujours déclenché (comportement
   pk existant, régression testée explicitement pour ce widget modifié).
4. Widget `map` sans `encodings` configuré → comportement actuel inchangé
   (aucune légende symbologie, couche en `fill` par défaut) — non-régression
   explicite sur les dashboards existants utilisant ce widget.
5. Les 72+ specs E2E existantes restent vertes.

| Risque | Garde-fou |
|---|---|
| `min === max` sur le domaine numérique (dataset à valeur constante ou une seule entité) | Expression MapLibre `interpolate` avec deux arrêts identiques provoquerait une erreur MapLibre (`stops must be strictly ascending`) — `buildMapPaint` détecte ce cas et retourne une couleur/taille constante, pas d'expression `interpolate` |
| Enregistrement sans géométrie (DataSource `features` malformée ou vide) | `detectGeometryKind` sur `records[0]?.geometry` undefined → repli `"polygon"`/`renderAs: "fill"` (comportement actuel identique à aujourd'hui), pas de crash |
| Couche existante déjà enregistrée dans un `MapConfig` (éditeur de carte complet) | `renderAs` absent ⇒ `"fill"` implicite dans `MapView.tsx`, strictement identique au code actuel — zéro régression possible sur l'éditeur de carte, qui ne construit jamais ce champ |
| Beaucoup de valeurs catégorielles distinctes (> 8) rendant la légende illisible | Non traité explicitement en v1 — cycle de palette au-delà de 8, légende peut afficher deux swatches de couleur identique pour des valeurs différentes (limite connue, cohérente avec l'absence de palette configurable, §1 non-buts) |
| Widget `map` existant sur des dashboards déjà publiés, sans `encodings` | `encodings` optionnel ; `ctx.data.records[0]?.geometry` non lu si aucun encoding n'est configuré (court-circuit), donc zéro requête `statistics` supplémentaire et zéro changement de couche pour ces configs |
