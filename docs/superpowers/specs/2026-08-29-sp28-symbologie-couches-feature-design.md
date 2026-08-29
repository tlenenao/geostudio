# Symbologie des couches `feature` (URL GeoJSON) dans l'éditeur de cartes (SP-28)

> Reliquat du lot Carte de la vague 4 (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`,
> chantiers 4.2/4.3), noté dans CLAUDE.md « À venir » : *« éditeur de
> symbologie pour les couches `kind: "feature"` dans `LayersPanel`
> (aujourd'hui `null` faute de `collectionId` — décision produit non
> tranchée) »*. Spec brainstormée et validée avec Tanguy le 2026-08-29.

## 1. Contexte & objectif

`MapLayer` a deux variantes pertinentes ici (`shell/src/api/types.ts:108-141`) :
`kind: "vector"` (tuiles MVT servies par le cœur, adossées à un
`collectionId`) et `kind: "feature"` (une simple `url` GeoJSON, sans
collection). SP-25/27 ont donné aux couches `vector` une symbologie
déclarative complète (`LayerSymbology` : couleur/taille/classes/palettes,
puis contour/opacité/icônes/étiquettes). Les couches `feature` en sont
restées privées : `LayerSymbologyEditor` (`shell/src/map/LayersPanel.tsx:57`)
retourne `null` dès que `collectionId` est absent, faute de schéma
interrogeable pour lister les champs ou calculer un domaine.

Vérifié contre le code avant d'écrire cette spec :

- **Aucun chemin d'ajout n'existe** pour une couche `feature` dans l'éditeur
  de cartes : `LayerPicker.tsx` ne produit ce `kind` qu'en repli
  (`toMapLayer`, ligne 35) si `source.kind` n'est ni `vector`, ni `raster`,
  ni `tiles3d` — et `useLayerSources`/`/harvest/layers` (core,
  `app/harvest/routes.py:175`) n'émettent jamais que du `raster`. Ce chantier
  doit donc **aussi** ajouter le moyen de créer une telle couche, sans quoi
  l'éditeur de symbologie resterait du code mort. Décidé en session : les
  deux ensemble.
- Le précédent existe déjà pour le **popup** : `LayerPopupEditor` (même
  fichier, ligne 12) gère le cas sans collection en tombant à
  `availableFields=[]` — l'auteur saisit le nom du champ à la main. C'est le
  patron à généraliser, pas à réinventer.
- Le **widget carte** (`shell/src/builder/widgets/mapWidget.tsx:179-227`,
  SP-27) a un autre précédent pour une couche `feature` sans schéma : il
  utilise `availableFields=[]`, garde `runStatistics` fonctionnel (car adossé
  à un `DataSource`/`datasetId` résolvable côté serveur), mais force
  `jenksAvailable={false}` et fait lever `sampleField` — Jenks a besoin de
  valeurs brutes qu'aucun endpoint de statistiques ne renvoie. **Ce chemin
  reste inchangé** (hors périmètre, cf. §2) : une couche `feature` de
  `LayersPanel` n'a **aucun** `DataSource` derrière elle, juste une `url` —
  la resolution est nécessairement différente.
- `MapSymbologyEditor` (`shell/src/map/MapSymbologyEditor.tsx:22-53`) n'a
  besoin, pour fonctionner, que de trois choses paramétrables par l'hôte :
  `availableFields: string[]`, `runStatistics: StatQueryFn` (accepte
  `{groupBy}` ou `{measures: [{field, agg: "min"|"max"|"percentile", p?,
  label}]}`, renvoie `DataRecord[]`), `sampleField: SampleFieldFn` (renvoie
  `number[]`, seulement pour Jenks). Rien dans le composant ne suppose une
  collection : ces trois fonctions sont déjà le seul point de variation entre
  les deux hôtes existants (commentaire ligne 18-21 de
  `MapSymbologyEditor.tsx`).
- `mapSymbology.ts` expose déjà `detectGeometryKind(geometry: unknown)` et
  `renderAsFor(geometryKind)` (lignes 193-202), utilisés par `mapWidget.tsx`
  pour déduire le rendu (`fill`/`circle`/`line`) d'une géométrie GeoJSON
  arbitraire — réutilisables tels quels.
- `MapView.tsx` ne fait la résolution de domaine/palette **qu'à
  l'enregistrement** (`symbology` est figé dans la config, appliqué de façon
  pure et synchrone au rendu — commentaire ligne 159-162). Au rendu, une
  couche `feature` est donnée telle quelle à MapLibre comme source GeoJSON
  native (`data: layer.url`) : **aucun fetch/parse côté application
  aujourd'hui**, MapLibre gère ça en interne. Ce chantier introduit donc le
  premier fetch+parse JS d'un GeoJSON par URL, mais uniquement côté auteur
  (éditeur), jamais au rendu runtime.
- `MapLayer.symbology` et `.popup` sur `kind: "feature"` sont déjà typés
  (`types.ts:139-140`) et le cœur les persiste sans schéma dédié
  (`symbology: dict | None`, non typé côté `core/app/configs/schemas.py`) —
  aucune migration nécessaire.

## 2. Périmètre

**Dans le périmètre :**

1. **Ajout d'une couche par URL GeoJSON** dans `LayerPicker.tsx` — titre +
   URL, même patron que le formulaire « tileset 3D par URL » déjà présent
   dans ce fichier (lignes 99-128).
2. **Un module nouveau, pur, sans dépendance réseau propre à l'app** :
   `shell/src/map/geojsonIntrospect.ts` — fetch + parse d'un GeoJSON, liste
   de champs, et implémentations de `StatQueryFn`/`SampleFieldFn` calculées
   en mémoire sur les entités déjà parsées.
3. **`LayerSymbologyEditor`** (`LayersPanel.tsx`) — remplace le
   `return null` par un vrai rendu pour `kind: "feature"`, avec
   `jenksAvailable={true}` (les valeurs sont locales : Jenks fonctionne
   réellement ici, contrairement au widget carte).
4. **`LayerPopupEditor`** (même fichier) — réutilise la même requête
   d'introspection pour peupler `availableFields` au lieu de rester à `[]`
   en permanence pour une couche `feature`.
5. Détection de géométrie à l'ajout (`renderAs`) pour qu'une couche de
   points/lignes ajoutée par URL ne tombe pas dans le défaut `"fill"` et ne
   reste pas invisible.

**Hors périmètre :**

- Le widget carte (`mapWidget.tsx`) : chemin distinct et déjà livré (SP-27),
  non touché. Le mettre à niveau (Jenks fonctionnel via une résolution
  différente) est un chantier séparé, non planifié ici.
- Tout proxy serveur ou validation d'URL (SSRF) : c'est déjà le navigateur
  (MapLibre) qui fetch nativement cette URL pour le rendu aujourd'hui — le
  fetch d'introspection ajouté ici a exactement la même surface de confiance,
  aucune n'est ajoutée.
- Inférence de type de champ (string/nombre/date) : `MapSymbologyEditor`
  ne consomme que des noms de champs (`string[]`), jamais de types — même
  périmètre que `LayerPopupEditor` aujourd'hui.
- Toute modification du schéma cœur ou de `MapLayer` : `symbology`/`popup`
  sur `kind: "feature"` existent déjà et round-trippent (§1).

## 3. Mécanisme

### 3.1 — `geojsonIntrospect.ts`

```ts
export async function fetchFeatureCollection(url: string): Promise<GeoJSONFeatureCollection>
export function listFields(fc: GeoJSONFeatureCollection): string[]
export function makeStatQueryFn(fc: GeoJSONFeatureCollection): StatQueryFn
export function makeSampleFieldFn(fc: GeoJSONFeatureCollection): SampleFieldFn
```

- `fetchFeatureCollection` : `fetch(url)`, rejette avec un message explicite
  si `!res.ok` ou si le JSON n'a pas `type: "FeatureCollection"`/`features`
  (même défense qu'un import GeoJSON existant, pas de nouvelle bibliothèque).
- `listFields` : union des clés de `feature.properties` sur **toutes** les
  entités (pas seulement la première — un GeoJSON hétérogène ne doit pas
  amputer la liste), triée pour un rendu stable.
- `makeStatQueryFn` couvre exactement les deux formes de requête consommées
  par `computeColorDomain`/`computeSizeDomain` (`mapSymbology.ts:369-417`) :
  - `{groupBy: field}` → valeurs distinctes de `properties[field]`
    (converties en chaîne), une ligne `DataRecord` par valeur
    (`{id: value, properties: {}}`), ordre de première apparition.
  - `{measures: [{field, agg, label, p?}]}` → une seule ligne
    `{id: "agg", properties: {[label]: valeur}}` ; `min`/`max` triviaux,
    `percentile` interpole sur les valeurs numériques finies triées de
    `field` (même définition que le cœur pour rester visuellement cohérent
    d'une couche `vector` à une couche `feature` — pas besoin de bit-à-bit
    identique, juste d'un percentile standard).
- `makeSampleFieldFn(field, limit)` : toutes les valeurs numériques finies de
  `field`, tronquées à `limit` — pas d'échantillonnage aléatoire nécessaire
  (les valeurs sont déjà toutes en mémoire, contrairement à
  `sampleCollectionField` côté cœur qui sonde une table potentiellement
  énorme).
- Un cas vide (aucune entité, champ absent) renvoie des structures
  dégénérées mais non `NaN`/`undefined` — même défense que
  `quantileBreaksFromRow` (`mapSymbology.ts:294-302`, `?? 0` partout) : pas
  de nouveau bug de config cassée à la SP-25/I1.

### 3.2 — Câblage dans `LayersPanel.tsx`

Un seul `useQuery(["feature-geojson", layer.url], () =>
fetchFeatureCollection(layer.url), { enabled: layer.kind === "feature" })`
partagé par `LayerPopupEditor` et `LayerSymbologyEditor` pour cette couche
(react-query dédoublonne par clé — un seul fetch réseau même si les deux
éditeurs sont montés simultanément, ce qui est le cas aujourd'hui).

- `LayerPopupEditor` : `availableFields = collectionId ? schema… :
  (featureGeojson.data ? listFields(featureGeojson.data) : [])`.
- `LayerSymbologyEditor` : ne retourne plus `null` pour `kind: "feature"`.
  `availableFields` comme ci-dessus. `runStatistics`/`sampleField` :
  - si `collectionId` → chemin existant, inchangé ;
  - sinon, si `featureGeojson.data` chargé → `makeStatQueryFn`/
    `makeSampleFieldFn(featureGeojson.data)` ;
  - sinon (en cours de chargement **ou** échec du fetch) → fonctions qui
    rejettent avec un message clair. C'est la dégradation naturelle vers le
    comportement actuel (`availableFields=[]`, tout calcul indisponible) :
    pas un second chemin à maintenir, juste l'état "pas encore de données"
    d'une seule et même requête.
  - `jenksAvailable={true}` inconditionnellement pour `kind: "feature"` :
    contrairement au widget carte, la fonction ne lève que si les données ne
    sont pas encore là, jamais par nature.

### 3.3 — Ajout par URL dans `LayerPicker.tsx`

Bloc supplémentaire, même forme que « Ajouter un tileset 3D par URL » :
titre + URL + bouton « Ajouter la couche ». À la soumission :

1. `fetchFeatureCollection(url)` (best-effort, awaited, bouton désactivé le
   temps de la requête).
2. Succès → `detectGeometryKind(fc.features[0]?.geometry)` puis
   `renderAsFor(...)` posé sur la nouvelle couche ; le résultat du fetch
   alimente le cache react-query sous la même clé `["feature-geojson", url]`
   que §3.2, donc l'ouverture immédiate du panneau de symbologie ne
   refait pas de requête.
3. Échec (CORS, 404, JSON invalide, GeoJSON vide) → la couche est quand même
   ajoutée, sans `renderAs` (défaut `"fill"`, comportement actuel), avec un
   message d'erreur inline sous le formulaire — ne jamais bloquer l'ajout
   d'une URL par ailleurs valide pour MapLibre mais pas pour notre `fetch`
   (ex. en-têtes d'authentification différents).

## 4. Tests

- `geojsonIntrospect.test.ts` (nouveau) : `groupBy`, chaque `agg`
  (`min`/`max`/`percentile` à plusieurs `p`), `sampleField` sur des valeurs
  non numériques mélangées, GeoJSON vide/malformé, union de champs sur des
  entités hétérogènes.
- `LayersPanel.test.tsx` : symbologie catégorielle/classée sur une couche
  `feature` avec `fetch` mocké ; dégradation propre si le fetch échoue.
- `LayerPicker.test.tsx` : ajout par URL, `renderAs` déduit de la géométrie,
  ajout malgré un fetch en échec.
- Une spec E2E Playwright (`shell/e2e/`) : ajouter une couche par URL
  GeoJSON (URL `data:` ou route de fixture locale — à trancher en plan),
  la styliser en catégoriel, vérifier le rendu — même exigence que toute
  feature visible (CLAUDE.md, « TDD systématique »).
- Régénération OpenAPI/types TS : **non nécessaire**, aucune route ni modèle
  cœur ne change (§1, dernier point) — le vérifier explicitement en fin de
  plan pour ne pas heurter le piège n°1 de CLAUDE.md par excès de prudence
  inutile.

## 5. Risques et limites connues

- Un GeoJSON très volumineux fetché deux fois (une fois par notre
  introspection, une fois par MapLibre en interne) double la bande passante
  pour cette couche à l'ouverture de l'éditeur. Accepté : c'est le prix de
  la parité de fonctionnalités, et la donnée est de toute façon chargée en
  entier par MapLibre pour le rendu (même ordre de grandeur).
- Une couche `feature` dont l'URL exige des en-têtes que notre `fetch` ne
  pose pas (ex. jeton dans un en-tête custom que MapLibre ne pose pas non
  plus) échouera de la même façon des deux côtés — pas une régression.
