# Symbologie dans l'éditeur de cartes (SP-25)

> Chantiers 4.2 « Symbologie dans l'éditeur de cartes » et 4.3 « Classes et
> palettes » du plan d'action `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`
> (§6, vague 4, lot Carte), suite directe de SP-24 (4.1, carte interrogeable),
> qui a posé `collectionId`/`geometryKind` sur chaque couche `vector` tuilée —
> c'est ce lien qui permet ici de calculer des bornes de classes sans charger
> toutes les features. Spec brainstormée et validée avec Tanguy le 2026-08-23.

## 1. Contexte & objectif

Le plan (lignes 387-388) demande deux choses : une couche `MapLayer` gagne une
symbologie déclarative compilée vers un paint MapLibre à l'affichage, au lieu
d'un `paint` brut écrit à la main (4.2) ; puis des classes (quantiles /
intervalles égaux / seuils naturels), un nombre de classes choisi par
l'auteur, et des palettes sélectionnables branchées sur le `Theme` existant
(4.3). Critère de sortie littéral : *une carte à 5 classes en quantiles, dans
la palette du thème du site, round-trippée en config et rendue à l'identique*.

Vérifié contre le code avant d'écrire cette spec :

- `shell/src/builder/widgets/mapSymbology.ts` **existe déjà**, mais n'est
  consommé que par le widget carte des apps/dashboards (`mapWidget.tsx`) —
  jamais par l'éditeur de carte standalone. Il calcule `detectGeometryKind`,
  `buildMapPaint` (couleur catégorielle/numérique-continue, taille) et
  `buildLegend`, à partir de domaines déjà résolus côté serveur (le widget
  interroge `/collections/{id}/aggregate` via `queryDataSource({type:
  "statistics", ...})`, jamais un scan client des features chargées — seul
  `geometryKind` vient d'un échantillon local).
- `LayersPanel.tsx` (éditeur de carte standalone, `MapEditorPage`) **n'a
  aucune UI de symbologie** : seulement visibilité, ordre, suppression et
  popup (SP-24). `MapLayer.paint` est un `Record<string, unknown>` brut, non
  éditable par l'auteur.
- `POST /collections/{collection_id}/aggregate` (`core/app/features/routes.py:240`)
  prend un `collection_id` **directement** — pas seulement via un item
  Dataset — et accepte déjà `min`/`max`/`percentile`/`bins` (SP-23). C'est
  exactement ce dont une couche `vector` tuilée a besoin pour calculer ses
  bornes, sans passer par un Dataset.
- `Theme` (`shell/src/api/types.ts:630`) ne porte que 6 couleurs d'UI
  (`primary`/`background`/`surface`/`text`/`muted`/`border`), aucune notion
  de palette de données. Il vit sur `AppConfig.theme` — un `MapConfig`
  standalone (item carte) n'a **aucun** champ theme. « Branché sur le Theme
  existant » ne peut donc pas signifier une carte standalone hors app/site :
  ça s'applique seulement quand la symbologie est éditée depuis le widget
  carte (qui, lui, a accès à l'`AppConfig.theme` englobant).

## 2. Périmètre

Les deux chantiers, avec **un élargissement assumé, tranché en session** :
**unification des deux surfaces**. `mapWidget.tsx` abandonne son mécanisme
actuel (`props.encodings`, domaines recalculés à chaque rendu via
`useQuery`) au profit du même champ déclaratif `symbology` que `MapLayer`,
édité par le **même** composant que `LayersPanel`. Raison : c'est le même
motif que le partage de `PopupEditor` en SP-24 (écart I2 de la revue finale
SP-23 — un garde-fou/une capacité écrit pour une surface et jamais reporté
sur sa jumelle) — construire deux mécanismes de symbologie parallèles dès
l'origine reproduirait exactement ce défaut par construction.

**Dans le périmètre :**

- Un type `LayerSymbology` déclaratif (couleur + taille), remplaçant
  `MapEncodings` (aujourd'hui limité au widget).
- Trois méthodes de classification pour la couleur numérique : `quantile`,
  `equalInterval`, `jenks` — en plus du mode `continuous` déjà existant
  (dégradé linéaire, inchangé). Nombre de classes choisi par l'auteur (2 à 9).
- Palettes curatées, sélectionnables par nom, plus une palette dérivée du
  thème (`theme-primary`) quand un thème est disponible (widget carte
  uniquement — jamais pour une carte standalone).
- Domaines et bornes **calculés une fois, figés dans la config** à
  l'enregistrement (§3.2) — jamais recalculés au rendu, y compris pour une
  carte publique anonyme.
- Nouvelle capacité `sample` sur `POST /collections/{id}/aggregate`, seule
  addition serveur nécessaire (quantile et intervalle égal se calculent
  entièrement avec les primitives déjà existantes).
- Un composant d'édition partagé, `MapSymbologyEditor`, monté sur
  `LayersPanel` **et** le `PropsPanel` du widget carte.
- Rendu : `buildMapPaint` étendu pour émettre une expression MapLibre `step`
  pour la couleur classée (en plus de `interpolate` pour le continu et
  `match` pour le catégoriel, inchangés) ; `buildLegend` étendu pour un
  swatch + libellé de plage par classe.

**Hors périmètre, explicitement :**

- **4.4 (étiquettes, contour, opacité, icônes)** et **4.5 (mesure, croquis)**
  — restent non planifiés après ce SP, comme prévu par le plan.
- **Extension du type `Theme`** avec une vraie notion de palette de données
  éditable (`Theme.dataPalettes` ou équivalent). Question produit non
  résolue (où éditer ces palettes ? quel item les possède pour une carte hors
  site ?), écartée en session pour ne pas faire déborder SP-25 sur un
  chantier thème non prévu. La palette `theme-primary` est **dérivée** de
  `theme.colors.primary` par calcul (§3.4), jamais stockée.
- **Classification de la taille.** Le champ `size` reste en interpolation
  continue (comportement actuel inchangé) — les classes/palettes ne
  s'appliquent qu'à l'encodage couleur, cohérent avec le sens du chantier
  4.3 (« classes et palettes » de choroplèthe).
- **Aperçu visuel en direct dans l'éditeur** (rendu miniature des classes
  pendant la saisie, au-delà de l'affichage textuel des bornes calculées).
  Non demandé par le critère de sortie du plan, qui porte sur le rendu carte
  final, pas sur l'expérience d'édition.
- **Migration des configs déjà publiées.** Le remplacement de
  `props.encodings` par `props.symbology` sur le widget carte est un
  changement cassant assumé (§4, précédent SP-24 §7 sur le retrait de la
  route Martin) : une app déjà publiée avec un widget carte colorié perd sa
  symbologie au prochain chargement (retombe sur un paint par défaut, pas
  d'erreur). `MapLayer.paint` (brut) reste un chemin de secours manuel
  intact pour les cartes standalone qui n'utilisent pas `symbology`.
- **Toute correction trouvée hors des fichiers déjà touchés** : notée en
  suivi non bloquant, pas corrigée ici (précédent constant de ce dépôt).

## 3. Mécanisme

### 3.1 — Modèle de données

`shell/src/builder/widgets/mapSymbology.ts` (module pur existant, étendu) :

```ts
export type PaletteId =
  | "categorical-a" | "categorical-b"
  | "sequential-blue" | "sequential-warm"
  | "theme-primary"; // proposée seulement si un thème est disponible (§3.4)

export type ColorClassification =
  | { method: "continuous" }
  | { method: "quantile" | "equalInterval" | "jenks"; classes: number }; // 2..9

export type ColorDomain =
  | { kind: "categorical"; values: string[] }
  | { kind: "numeric-continuous"; min: number; max: number }
  | { kind: "numeric-classed"; breaks: number[] }; // k+1 bornes pour k classes

export type LayerSymbology = {
  color?: {
    field: string;
    mode: "categorical" | "numeric";
    classification?: ColorClassification; // numérique seulement ; absent = continuous
    palette: PaletteId;
    domain: ColorDomain;   // figé à l'enregistrement (§3.2), jamais recalculé au rendu
    computedAt: string;    // ISO 8601, affiché dans l'éditeur ("Classes calculées le …")
  };
  size?: {
    field: string;
    domain: { min: number; max: number }; // figé, même règle
    computedAt: string;
  };
};
```

`LayerSymbology` remplace `MapEncodings` (qui n'existait que côté widget).
Côté types partagés (`shell/src/api/types.ts`) :

- `MapLayer` kind `"vector"` et `"feature"` gagnent `symbology?:
  LayerSymbology`, en plus du `paint?: Record<string, unknown>` existant
  (inchangé, reste un chemin manuel : quand `symbology` est présent, il
  l'emporte à la compilation du paint — §3.5 — `paint` brut n'est alors
  jamais lu).
- `mapWidget.tsx` : `props.symbology` (nouvelle forme) remplace
  `props.encodings` (§2, changement cassant assumé).
- Côté cœur, `core/app/configs/schemas.py` porte le même champ sur ses
  variantes `MapLayer`/widget carte — même précédent que `popup` en SP-24
  §3.3 : sans lui, `saveMapConfig`/`updateItem` perdrait `symbology` en
  silence à l'enregistrement.

### 3.2 — Calcul des domaines et des bornes

Trois cas, tous **calculés à la demande de l'auteur** (bouton « Recalculer
les classes/tailles »), jamais automatiquement, jamais au rendu :

1. **Catégoriel** — `queryDataSource({type: "statistics", groupBy: field,
   ...})`, déjà le mécanisme du widget aujourd'hui. Résultat : liste de
   valeurs distinctes, figée dans `domain.values`.
2. **Numérique continu ou classé quantile/intervalle égal** — un **seul**
   appel `queryDataSource({type: "statistics", measures: [...]})` :
   - continu : `measures: [{agg:"min"}, {agg:"max"}]` → `domain =
     {kind:"numeric-continuous", min, max}`.
   - `equalInterval`, k classes : mêmes deux mesures, bornes dérivées
     **côté client** : `breaks[i] = min + i·(max−min)/k` pour `i = 0..k`.
   - `quantile`, k classes : `measures: [{agg:"min"}, {agg:"percentile",
     p:100/k}, {agg:"percentile", p:200/k}, ..., {agg:"max"}]` — k+1 mesures
     en un seul aller-retour réseau, aucune nouvelle capacité serveur (SP-23
     a déjà livré `percentile`).
3. **Numérique classé jenks, k classes** — nécessite un échantillon de
   valeurs, qui n'existe pas aujourd'hui. Nouvelle capacité côté cœur
   (§3.3), puis calcul du dynamic programming de Fisher-Jenks **côté
   client**, sur l'échantillon borné (≤ 2000 points) : `O(n²·k)` reste sous
   ~40M opérations pour `n=2000, k=9` — largement dans un budget navigateur
   raisonnable, pas besoin de l'algorithme accéléré (SMAWK/Ckmeans).

Le résultat (`domain` + `computedAt`) est écrit dans `LayerSymbology`
seulement quand l'auteur enregistre la carte/app — jamais avant, jamais en
arrière-plan. Une carte publiée avec une symbologie figée ne déclenche
**aucun** appel réseau d'agrégat à l'affichage : `MapView` compile le paint
depuis les valeurs déjà stockées.

### 3.3 — Cœur : nouvelle capacité `sample`

`core/app/analytics/aggregate.py` (même fichier que `bins`/`percentile`,
SP-23) :

```python
class AggregateRequestBody(BaseModel):
    ...
    sample: int | None = None  # 1..2000
```

Règles de validation (`_validate_fields`, même fonction que `bins`) :

- `sample` requiert `field`, refuse `groupBy` et `bins` en même temps (même
  esprit que la règle existante `bins` vs `groupBy`).
- Borné `1 <= sample <= 2000`.
- SQL : `SELECT TRY_CAST(<field> AS DOUBLE) AS value FROM (<cte de dédup
  CDC existant>) WHERE value IS NOT NULL USING SAMPLE <n> ROWS`. Réutilise
  verbatim la CTE de dédoublonnage déjà construite par
  `run_collection_aggregate` — aucun nouveau chemin de lecture GeoParquet.
- Réponse : `{"rows": [{"value": <float>}, ...]}` (forme distincte de
  `{categoryKey, rows}` du chemin groupBy — `sample` ne groupe rien).
- Même porte d'autorisation que le reste de la route
  (`get_current_user_optional` + `get_readable_collection`) : aucun
  changement d'auth, `sample` est un mode de plus sur une route déjà
  auditée par SP-24/SP-23.

### 3.4 — Palettes

Nouveau module pur `shell/src/builder/widgets/palette.ts` :

```ts
type ResolvedPalette =
  | { kind: "categorical"; colors: string[] }
  | { kind: "sequential"; low: string; high: string };

export const CURATED_PALETTES: Record<
  Exclude<PaletteId, "theme-primary">,
  ResolvedPalette
>;
// "categorical-a" = CATEGORICAL_PALETTE actuelle (8 couleurs, inchangée).
// "categorical-b", "sequential-blue" (= NUMERIC_COLOR_LOW/HIGH actuelles),
// "sequential-warm" : nouvelles.

export function resolvePalette(
  id: PaletteId,
  themeColors: ThemeColors | undefined,
): ResolvedPalette | null;
// "theme-primary" sans theme disponible → null (l'éditeur ne doit pas
// proposer l'option, jamais retomber silencieusement sur une autre palette).
// "theme-primary" avec theme → rampe séquentielle dérivée de primary
// (teinte claire → primary, via décalage de luminosité HSL), ou variantes
// de teinte pour le catégoriel.

export function colorsForClasses(palette: ResolvedPalette, n: number): string[];
// categorical : découpe/répète sa liste (comme paletteColor() aujourd'hui).
// sequential : n arrêts également espacés, interpolation RGB linéaire
// low → high (aucune bibliothèque : lerp maison sur les composantes R/G/B).
```

### 3.5 — Rendu : `buildMapPaint` étendu

Le cas classé (numérique + `classification.method !== "continuous"`) émet :

```ts
paint[prop] = [
  "step",
  ["get", field],
  colors[0],
  breaks[1], colors[1],
  breaks[2], colors[2],
  // ...
  breaks[k-1], colors[k-1],
];
```

Les cas `continuous` (interpolate, inchangé) et catégoriel (`match`,
inchangé dans sa forme — seule la source des couleurs change, désormais
`colorsForClasses(resolvePalette(...), n)` au lieu des constantes de
module) restent tels quels. `MapView` n'a aucun changement à faire : il
consomme toujours `layer.paint` — c'est la fonction de compilation
(appelée à la sauvegarde, résultat stocké tel quel comme `paint` généré)
qui change, pas le point de rendu.

Point de câblage exact : `MapLayer.paint` reste le champ que `MapView` lit.
Quand `layer.symbology` est présent, le **paint effectif** est recompilé
depuis `symbology` à chaque `onChange` de l'éditeur (aperçu textuel des
bornes, pas de rendu carte live — hors périmètre §2) et **écrit dans
`layer.paint`** à l'enregistrement — `paint` devient un champ dérivé/généré
quand `symbology` est présent, encore éditable à la main quand il est
absent. Ainsi `MapView` n'a besoin d'aucune connaissance de `symbology` :
un seul chemin de rendu, cohérent avec le patron déjà établi par SP-24 pour
les couches `vector` sans géométrie connue (sous-couches par type).

`buildLegend` étendu : un swatch + un libellé de plage par classe
(`"12 – 45"`, dernière classe fermée sur `max` inclus) pour le cas classé,
en plus des branches catégorielle et continue existantes (inchangées).

### 3.6 — Éditeur partagé : `MapSymbologyEditor`

Nouveau composant, même patron que `PopupEditor` (SP-24 §3.6) — pur,
aucune hypothèse sur son hôte :

```ts
function MapSymbologyEditor(props: {
  value: LayerSymbology | undefined;
  availableFields: string[];      // [] côté widget (même patron que PopupEditor)
  themeColors: ThemeColors | undefined; // undefined pour une carte standalone
  onComputeColorDomain: (params: {
    field: string;
    mode: "categorical" | "numeric";
    classification?: ColorClassification;
  }) => Promise<ColorDomain>;
  onComputeSizeDomain: (field: string) => Promise<{ min: number; max: number }>;
  onChange: (value: LayerSymbology | undefined) => void;
}): JSX.Element
```

`onComputeColorDomain`/`onComputeSizeDomain` sont les deux seules choses qui
diffèrent par hôte (résolution `collectionId` direct vs `datasetId`
résolu) :

- `LayersPanel.tsx` (couche `vector`/`feature` avec `layer.collectionId`
  disponible pour `vector`) : `client.queryDataSource({type: "statistics",
  service: "core", layer: layer.collectionId, query: {...}})`, exactement
  le mécanisme déjà utilisé par `LayerPopupEditor` pour le schéma de
  colonnes (§3.5 de SP-24). Pour `jenks`, un appel supplémentaire
  `client.queryDataSource({type: "statistics", ..., query: {sample: n,
  field}})`.
- `mapWidget.tsx`'s `PropsPanel` : même mécanisme que ce qu'il fait déjà
  aujourd'hui (`datasetId`-résolu), simplement rebranché sur ce composant
  partagé au lieu de son UI inline actuelle.

Contenu du composant : sélecteur de champ couleur, mode (catégoriel/
numérique), pour numérique un sélecteur de méthode (continu / quantile /
intervalles égaux / seuils naturels) + nombre de classes (2-9, masqué si
continu), sélecteur de palette (liste filtrée par `themeColors !==
undefined` pour l'option `theme-primary`), bouton « Recalculer les
classes » (appelle `onComputeColorDomain`, écrit `domain`+`computedAt`),
affichage textuel des bornes calculées et de leur date, sélecteur de champ
taille + bouton « Recalculer » séparé.

### 3.7 — Sites d'appel

- `LayersPanel.tsx` : un bloc symbologie par couche `vector`/`feature`
  (comme le bloc popup existant), utilisant `MapSymbologyEditor` avec
  `themeColors: undefined` (aucune notion de thème pour une carte
  standalone, §1) et le schéma déjà chargé pour le popup (`availableFields`
  partagé).
- `mapWidget.tsx`'s `PropsPanel` : remplace le bloc `encodings` actuel par
  `MapSymbologyEditor`, avec `themeColors` lu depuis l'`AppConfig.theme`
  englobant. Vérifié : `WidgetDefinition["PropsPanel"]`
  (`shell/src/builder/registry.ts:33-37`) ne reçoit aujourd'hui que
  `{props, onChange, dataSources}` — aucun accès au thème. La signature
  gagne un champ `theme: Theme`, threadé depuis `AppBuilderPage.tsx` (qui a
  déjà `draft.theme`) à travers le wrapper `shell/src/builder/PropsPanel.tsx`
  jusqu'à `def.PropsPanel`. Changement additif par typage structurel : les
  ~22 autres widgets, qui ne déstructurent pas `theme`, continuent de
  compiler et de fonctionner sans y toucher — seul `mapWidget.tsx`
  consomme le nouveau champ.
- `mapWidget.tsx`'s `Component` : au lieu de reconstruire `colorDomain`/
  `sizeDomain` par `useQuery` à chaque rendu, lit directement
  `props.symbology` (déjà figé) et appelle `buildMapPaint`/`buildLegend`
  avec ce domaine stocké — suppression de `useNumericDomain` et des deux
  `useQuery` de domaine dans le composant de rendu (ils ne survivent que
  dans `PropsPanel`, côté édition).

## 4. Décisions prises en session (2026-08-23)

1. **Unification des deux surfaces** (widget carte + éditeur de carte
   standalone) sur un seul type `LayerSymbology` et un seul composant
   d'édition. Écarté : garder le widget sur son mécanisme actuel et scoper
   SP-25 à `LayersPanel` seul — aurait rouvert la classe de défaut I2/SP-23.
2. **Jenks calculé côté client sur un échantillon serveur borné** (`sample`,
   ≤ 2000 valeurs), plutôt que reporté hors périmètre. Le calcul est une
   approximation assumée sur un très gros jeu de données (précédent
   accepté : QGIS/ArcGIS échantillonnent aussi au-delà d'un certain volume).
3. **Nouvelle capacité `sample` sur la route d'agrégat existante**, plutôt
   qu'une réutilisation de `GET /collections/{id}/items` (poids réseau de
   la géométrie/toutes les propriétés pour un usage purement statistique)
   ou une nouvelle route dédiée.
4. **Bornes et domaines figés à l'enregistrement**, jamais recalculés au
   rendu — y compris pour le domaine catégoriel et le min/max continu du
   widget (qui, eux, étaient dynamiques jusqu'ici). Cohérent avec le
   critère de sortie du plan (« round-trippée … et rendue à l'identique »)
   et avec l'esprit de la garde de coût I3/SP-24 : aucun appel d'agrégat au
   rendu d'une carte publique.
5. **Palettes curatées codées en dur + une palette dérivée de
   `theme.colors.primary` par calcul**, plutôt qu'une extension de schéma
   `Theme.dataPalettes`. Écarté pour ne pas ouvrir une question produit non
   résolue (où éditer des palettes de thème ? quel item les possède hors
   site ?) qui ferait déborder SP-25.
6. **Classification limitée à la couleur**, la taille reste en
   interpolation continue. Cohérent avec le sens de « classes et palettes »
   (choroplèthe), pas demandé par le plan pour la taille.
7. **`paint` reste un champ dérivé/généré à la compilation quand
   `symbology` est présent**, plutôt qu'un second champ de rendu parallèle
   dans `MapView` — un seul point de lecture pour le rendu carte, cohérent
   avec le patron déjà en place.

## 5. Ordre d'exécution recommandé

Le cœur d'abord (le shell ne peut pas prouver Jenks sans l'échantillon) :

1. `sample` sur `AggregateRequestBody`/`aggregate.py` (+ tests
   `@pytest.mark.postgis`).
2. Régénération OpenAPI + types TS.
3. `LayerSymbology`/`ColorDomain`/`ColorClassification`/`PaletteId` dans
   `shell/src/api/types.ts` et `mapSymbology.ts` ; côté cœur,
   `configs/schemas.py` gagne le même champ `symbology` (round-trip, même
   précédent que `popup`/SP-24).
4. `palette.ts` (module pur, TDD : lerp RGB, dérivation `theme-primary`).
5. `mapSymbology.ts` : classification (`quantile`/`equalInterval`
   côté client ; `jenks` — Fisher DP), extension de `buildMapPaint`/
   `buildLegend` pour le cas classé.
6. `MapSymbologyEditor` (module pur de présentation + logique de saisie),
   testé isolément avec des `onComputeXDomain` mockés.
7. Câblage `LayersPanel.tsx` (implémentation `onComputeColorDomain` via
   `collectionId`).
8. Câblage `mapWidget.tsx` (`PropsPanel` sur le composant partagé,
   `Component` lisant `props.symbology` figé au lieu des `useQuery` de
   domaine) — retrait de `props.encodings`, `MapEncodings`,
   `useNumericDomain` et des deux `useQuery` de domaine dans `Component`.
9. Spec E2E de la preuve du plan : 5 classes en quantiles sur une couche
   tuilée, palette choisie, enregistrement, rechargement, rendu identique.

## 6. Validation & preuves de sortie

1. **La preuve du plan**, en spec E2E Playwright : auteur une couche tuilée
   avec 5 classes en quantiles et une palette nommée dans `LayersPanel`,
   enregistre, recharge la carte, vérifie que les mêmes 5 couleurs/bornes
   sont rendues (pas de nouvel appel d'agrégat au rechargement — assertion
   réseau, même patron que les preuves E2E précédentes).
2. `core/tests/test_analytics_aggregate.py` (ou fichier équivalent) : cas
   `sample` — borne rejetée hors `[1, 2000]`, mutuelle exclusion avec
   `groupBy`/`bins`, exclusion des `NULL`, `field` requis.
3. `mapSymbology.test.ts` : bornes quantile/intervalle égal exactes contre
   un jeu de valeurs connu ; Jenks contre un petit fixture aux bornes
   calculées à la main ; expression `step` produite correcte pour un cas
   classé à 3 classes ; comportement `continuous`/catégoriel inchangé
   (régression).
4. `palette.test.ts` : interpolation RGB (bornes exactes aux extrémités,
   valeurs intermédiaires), dérivation `theme-primary` (présente/absente
   selon `themeColors`), `colorsForClasses` sur catégoriel (découpe/répète).
5. `MapSymbologyEditor.test.tsx` : rendu conditionnel de l'option
   `theme-primary`, appel de `onComputeColorDomain` avec les bons
   paramètres selon la méthode choisie, écriture de `domain`+`computedAt`
   dans `onChange`, masquage du sélecteur de classes en mode continu.
6. Régression widget carte : un test prouve que `Component` ne déclenche
   plus aucun `useQuery` de domaine (lecture directe de `props.symbology`).
7. Portes habituelles. Cœur : `uv run pytest` sans baisse par rapport à la
   référence mesurée en fin de SP-24 (1868 passed / 5 skipped),
   `ruff check`, `ruff format --check`, `mypy --strict` (4 modules),
   `lint-imports`, couverture ≥ 85. Shell : `npm run lint`,
   `format:check`, `test` (référence 159 fichiers / 1387 tests), `build`,
   `e2e`, couverture ≥ 88 (mesurée après nettoyage de `dist/`/
   `dist-export/`, piège documenté SP-22/SP-23/SP-24).
8. OpenAPI et types TS régénérés, diff non vide et committé (`sample` est
   un champ nouveau sur une route déjà montée inconditionnellement).

## 7. Risques et limites connues

- **Jenks est une approximation** sur un échantillon borné à 2000 valeurs
  pour une collection volumineuse — pas le résultat exact qu'un calcul sur
  la population complète donnerait. Assumé (§4).
- **Changement cassant** sur `mapWidget.tsx` : toute app déjà publiée avec
  une symbologie de widget carte configurée (`props.encodings`) perd cette
  configuration au prochain chargement après ce SP (§2). À écrire dans les
  notes de version, même précédent que le retrait de Martin en SP-24.
- **Palettes figées dans le code**, pas éditables par l'auteur au-delà du
  choix parmi la liste curatée + la dérivée du thème. Une vraie demande de
  palette personnalisée resterait hors périmètre (renverrait à la question
  `Theme.dataPalettes` écartée en §2).
- **Aucun aperçu carte live pendant l'édition** — seules les bornes
  calculées sont affichées en texte ; l'auteur voit le résultat en
  rafraîchissant la carte après enregistrement.
- **Domaines figés = données potentiellement périmées.** Une collection qui
  évolue après le calcul des classes ne met à jour ni les bornes ni la
  légende tant que l'auteur ne rouvre pas l'éditeur et ne recalcule pas
  explicitement (§4, décision assumée pour éviter tout appel d'agrégat au
  rendu).
