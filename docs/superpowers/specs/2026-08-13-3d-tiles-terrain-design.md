# 3D — `Tile3DLayer` + terrain `raster-dem` (design)

> **Date : 2026-08-13 · Statut : validé (brainstorm)**
> Reste de la vision post-v0.1 (feuille de route §SP-17, arbitrage **A24**).
> **Non planifié, non numéroté** : SP-17 a été exécuté sous les noms SP-17a
> (socle export Playwright/`PrintLayout`) et SP-17b (`ReportSchedule`) sans
> couvrir la 3D — cf. `CLAUDE.md` § Feuille de route, « À venir ». Ce
> document couvre uniquement le contenu 3D de l'A24 d'origine, pas
> l'impression (déjà livrée).
>
> Références : feuille de route
> (`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-17 « Contenu
> 3D », arbitrage A24) · `CLAUDE.md` (règles d'architecture #2/#3, arbitrages
> figés) · `shell/src/map/MapView.tsx` (overlay deck.gl `MapboxOverlay` déjà
> intégré à MapLibre, réutilisé tel quel — c'est la prémisse même de l'A24)
> · `core/app/configs/schemas.py` (`MapLayer`, `MapConfig`, `MapView`
> Pydantic — à ne pas confondre avec le composant React `MapView` du shell).

## 1. Objectif & non-buts

**Objectif.** Un auteur de carte peut ajouter une couche 3D Tiles (tuiles
OGC/Cesium via `tileset.json`) et activer un terrain élevé (DEM
`raster-dem`), tous deux hébergés **en dehors** de GeoStudio, régler
pitch/bearing depuis l'éditeur, sauvegarder cette caméra, et un visiteur
retrouve exactement cette vue 3D au chargement.

**Non-buts explicites** (périmètre resserré par rapport à l'A24 d'origine,
tranché en brainstorm 2026-08-13) :

- **Hébergement de tilesets 3D Tiles uploadés** (zip → S3 → item). Il
  n'existe aujourd'hui aucun pipeline d'hébergement de fichiers opaques
  (l'ingestion SP-6 parse des features dans des collections, ce n'est pas
  la même chose) — construire ce pipeline est un chantier à part entière,
  pas un sous-produit de l'affichage 3D. Un tileset est référencé par URL
  externe uniquement.
- **Terrain servi par notre propre TiTiler** depuis un DEM COG hébergé chez
  nous. TiTiler est déjà provisionné dans le compose (credentials MinIO
  prêts) mais jamais réellement utilisé à ce jour ; produire des tuiles
  `raster-dem` encodées terrain-RGB depuis TiTiler 0.18.4 n'est pas garanti
  trivial (rio-tiler ne fait pas nativement l'encodage terrarium/mapbox à
  partir d'un DEM brut) — risque technique non résolu, hors périmètre tant
  qu'une source externe déjà encodée suffit. Le terrain pointe vers une URL
  externe uniquement, comme les 3D Tiles.
- **Encodage `mapbox`** pour le terrain — seul `terrarium` (convention
  ouverte, ex. AWS Terrain Tiles) est supporté en v1 ; `mapbox` s'ajoute
  plus tard si un besoin réel apparaît (union discriminée déjà extensible
  côté schéma, cf. §2).
- **Conversion 3D** (py3dtiles, nuages de points) — explicitement différée
  par l'A24 elle-même, non concernée par ce document.
- **Outil MCP** dédié — aucun outil MCP n'expose `MapConfig` aujourd'hui
  (`explain_dataset`/`explain_pipeline`/etc. ne touchent pas les cartes) ;
  ne pas en créer un pour ce seul incrément.
- **Généralisation de l'ajout manuel par URL** dans `LayerPicker` à tous les
  `kind` — le formulaire ajouté (§4) est scopé à `tiles3d` seulement ; les
  couches `deck` restent, comme aujourd'hui, non ajoutables depuis
  l'éditeur (limitation préexistante, pas creusée ici).

Le modèle reste additif : `tiles3d` est un nouveau variant de l'union
`MapLayer`, `terrain` un nouveau champ optionnel de `MapConfig` — rien
n'est retiré ni changé de forme pour les couches/cartes existantes.

## 2. Modèle de données

**`MapLayer`** (shell `shell/src/api/types.ts`) gagne un variant
`kind: "tiles3d"`, réutilisant le champ `url` déjà porté par `kind:
"feature"` (un seul endpoint, pas un template de tuiles) :

```ts
export type MapLayer =
  | { id: string; title: string; visible: boolean; kind: "vector"; tilesUrl: string; sourceLayer: string; paint?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "raster"; tilesUrl: string; opacity?: number }
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown>; renderAs?: "fill" | "circle" | "line" }
  | { id: string; title: string; visible: boolean; kind: "deck"; deckType: "heatmap" | "hexbin" | "column"; dataUrl: string; props?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "tiles3d"; url: string };
```

**`MapConfig`** gagne un champ `terrain` optionnel, nesté directement (pas
traité comme `printLayout`, qui est un champ sibling top-level de
`BuilderConfig` partagé par map/app/dashboard/site — le terrain n'a de sens
que pour une carte, donc reste dans `MapConfig` lui-même) :

```ts
export type MapTerrainConfig = { tilesUrl: string; encoding: "terrarium"; exaggeration?: number };
export type MapConfig = {
  basemap: BaseMap;
  view: MapViewport;
  layers: MapLayer[];
  printLayout?: PrintLayoutConfig | null;
  terrain?: MapTerrainConfig | null;
};
```

`tilesUrl` (et non `url`) par cohérence avec `vector`/`raster`, qui portent
déjà un template `{z}/{x}/{y}` sous ce nom — le terrain est aussi un
template de tuiles, pas un endpoint unique.

**`MapViewport`** gagne `pitch?: number` et `bearing?: number` (défaut 0
si absents), persistés au même niveau que `center`/`zoom`.

Côté cœur (`core/app/configs/schemas.py`) :

```python
class MapLayer(BaseModel):
    id: str
    title: str
    visible: bool = True
    kind: Literal["vector", "raster", "feature", "deck", "tiles3d"]
    tilesUrl: str | None = None
    sourceLayer: str | None = None
    url: str | None = None
    opacity: float | None = None
    deckType: str | None = None
    dataUrl: str | None = None
    paint: dict | None = None
    props: dict | None = None
    # aucun nouveau champ : tiles3d réutilise `url` déjà porté par "feature"

class MapTerrain(BaseModel):
    tilesUrl: str
    encoding: Literal["terrarium"] = "terrarium"
    exaggeration: float | None = None

class MapView(BaseModel):   # modèle Pydantic — pas le composant React shell du même nom
    center: tuple[float, float]
    zoom: float
    pitch: float | None = None
    bearing: float | None = None

class MapConfig(BaseModel):
    basemap: BaseMap
    view: MapView
    layers: list[MapLayer] = Field(default_factory=list)
    terrain: MapTerrain | None = None
```

Pas de nouvelle validation croisée par `kind` (ex. « `tiles3d` exige `url`
non vide ») : aucune n'existe aujourd'hui pour vector/raster/feature/deck
malgré des champs tout aussi requis en pratique — cohérence délibérée avec
l'existant plutôt qu'une garde asymétrique introduite seulement pour le
nouveau `kind`. Le formulaire d'ajout côté shell (§4) empêche déjà la
soumission d'une URL vide, ce qui couvre le chemin d'auteur normal.

## 3. Rendu — `shell/src/map/MapView.tsx`

**Nouvelles dépendances** (`shell/package.json`) : `@deck.gl/geo-layers`
(contient `Tile3DLayer`) + `@loaders.gl/tiles` (`Tiles3DLoader`) +
`@loaders.gl/core`, alignées sur la ligne `9.0.x` déjà utilisée par
`@deck.gl/core`/`@deck.gl/layers`/`@deck.gl/aggregation-layers`/
`@deck.gl/mapbox` côté deck.gl, et une release `4.x` de loaders.gl
compatible (version exacte résolue à l'implémentation — pas de deuxième
version de deck.gl à faire cohabiter, c'est tout l'intérêt de l'A24).

**Couches 3D Tiles.** `applyLayers` (le chemin MapLibre natif, sources/
layers ajoutés directement sur `maplibregl.Map`) ignore `kind ===
"tiles3d"`, exactement comme il ignore déjà `kind === "deck"` — ces deux
kinds ne vivent jamais dans ce chemin. `applyDeckLayers` est étendu : en
plus des couches `deck`, il construit un `Tile3DLayer({ id: layer.id, data:
layer.url, loader: Tiles3DLoader })` pour chaque couche `tiles3d` visible,
ajouté au **même** `MapboxOverlay` déjà monté sur la carte. C'est
précisément la prémisse de l'A24 : un seul overlay/contexte WebGL partagé
entre MapLibre et deck.gl, pas de deuxième moteur de rendu.

**Terrain.** Sur `map.on("load")`, puis à chaque changement de
`config.terrain` (nouvel effect miroir de celui déjà présent pour
`config.layers`) :

- si `config.terrain` est présent → `map.addSource("__terrain__", { type:
  "raster-dem", tiles: [terrain.tilesUrl], tileSize: 256, encoding:
  "terrarium" })` puis `map.setTerrain({ source: "__terrain__",
  exaggeration: terrain.exaggeration ?? 1 })` ;
- sinon → `map.setTerrain(null)` et retrait de la source si elle existe
  (même discipline de nettoyage que le rollback déjà fait pour une couche
  MapLibre en échec dans `applyLayers`).

**Caméra.** Correction par rapport à la prémisse initiale du brainstorm :
`dragRotate`/`pitchWithRotate`/`touchPitch` sont **déjà actifs par défaut**
dans MapLibre GL JS — le constructeur `Map` de `MapView.tsx` ne les
désactive nulle part, donc aucune activation conditionnelle liée à la
présence d'une couche 3D/d'un terrain n'est nécessaire. Ce qui manque
réellement est la **persistance** :

- le constructeur `maplibregl.Map` reçoit `pitch: config.view.pitch ?? 0`
  et `bearing: config.view.bearing ?? 0` en plus de `center`/`zoom` ;
- le handler `moveend` existant (qui alimente `onViewChange`) est étendu
  pour renvoyer aussi `map.getPitch()`/`map.getBearing()` — `moveend` se
  déclenche déjà pour un pitch/bearing changé, pas seulement un pan/zoom,
  donc aucun nouvel event listener n'est nécessaire ;
- `MapViewHandle.flyTo` accepte optionnellement `pitch`/`bearing` en plus
  de `center`/`zoom` — un seul chemin pilote la caméra de façon
  programmatique (sliders de l'éditeur *et* navigation `story`
  `onEnter`/`flyTo` existante), jamais deux mécanismes divergents.

## 4. UI éditeur (`shell/src/pages/MapEditorPage.tsx` et alentours)

- **`LayerPicker`** : nouveau petit formulaire « Ajouter un tileset 3D par
  URL » (titre + URL `tileset.json`, bouton désactivé tant que l'un des
  deux champs est vide) affiché sous la liste catalogue existante
  (`useLayerSources`). Premier chemin d'ajout manuel par URL de l'éditeur —
  scopé à `tiles3d` uniquement (cf. non-but §1).
- **`TerrainPanel`** (nouveau composant, même patron que
  `PrintLayoutPanel` : `value`/`onChange` contrôlés, pas d'état interne
  propre) : case à cocher « Activer le terrain 3D » qui révèle, une fois
  cochée, un champ URL de tuiles et un champ numérique exaggeration
  (défaut 1). L'encodage n'est pas un sélecteur (`terrarium` seul supporté
  en v1, cf. §1) — juste une mention informative dans le panneau.
- **Caméra** : deux `<input type="range">` (pitch 0–60°, bearing 0–360°)
  et un bouton « Réinitialiser en 2D » (pitch=0, bearing=0), ajoutés dans
  l'aside de `MapEditorPage`, pilotant `MapViewHandle.flyTo` — le retour
  visuel (position réellement atteinte) vient du `moveend` étendu (§3), pas
  d'un état local dupliqué.
- **`MapLegend`** : une couche `tiles3d` visible apparaît dans la légende
  comme n'importe quelle autre couche (son `title`, rien de spécifique). Le
  terrain n'apparaît pas en légende — ce n'est pas une entrée de
  `MapConfig["layers"]`.
- **Mode `exportRender`** (SP-17a) : `MapEditorPage` rend déjà une branche
  dédiée pour la capture Playwright ; `MapView` y est utilisé sans
  changement de props pour ce document — une carte avec 3D Tiles/terrain se
  capture donc automatiquement à travers le même chemin d'export existant,
  aucune modification requise dans cette branche.

## 5. Tests

- **`MockDeckgl`** (helper de test existant, `shell/src/test/MockDeckgl.ts`)
  gagne un mock `Tile3DLayer` construit sur le même patron que
  `HeatmapLayer`/`HexagonLayer`/`ColumnLayer` ; `Tiles3DLoader` est mocké
  par un objet factice (jamais réellement invoqué en test, seulement passé
  en `loader:`).
- **`MapView.test.tsx`** : une couche `tiles3d` visible produit un
  `Tile3DLayer` dans l'overlay (miroir des tests existants pour
  heatmap/hexbin/column) ; une couche `tiles3d` non visible en est absente ;
  un `config.terrain` présent appelle `addSource`/`setTerrain` avec les
  bons paramètres ; son retrait appelle `setTerrain(null)` ; `moveend`
  relaie `pitch`/`bearing` dans `onViewChange`.
- **Tests composants** : nouveau formulaire d'ajout par URL de
  `LayerPicker` (soumission désactivée si champ vide, layer bien ajouté au
  bon format) ; `TerrainPanel` (toggle, champs révélés/masqués) ; sliders
  caméra + bouton reset de `MapEditorPage`.
- **E2E Playwright** (spec existante `map-editor` étendue, pas de nouvelle
  spec dédiée — c'est une extension de l'édition de carte déjà couverte,
  pas une nouvelle feature de navigation) : ajouter un tileset 3D par URL,
  activer le terrain avec une URL de test, régler pitch/bearing, sauver,
  recharger la page → tout est restitué à l'identique. Les 13+ specs E2E
  existantes restent vertes (aucun champ existant retiré ni changé de
  forme).
- **Explicitement hors CI** : le critère d'acceptation de l'A24 d'origine
  (« tileset 3D Tiles public navigable à > 30 fps sur un poste moyen »)
  contre un vrai tileset public — vérification manuelle ponctuelle avant de
  considérer l'incrément livré, le rendu WebGL réel et sa fluidité n'étant
  pas mesurables de façon fiable en Chromium headless CI. Ne bloque pas la
  CI ; bloque la clôture manuelle de l'incrément dans `CLAUDE.md`.

## 6. Risques

| Risque | Garde-fou |
|---|---|
| Version loaders.gl incompatible avec la ligne deck.gl 9.0.x déjà installée | Résolution de version faite à l'implémentation contre le lockfile existant, pas figée ici ; test unitaire `Tile3DLayer` mocké ne dépend pas de la résolution réelle des tuiles donc ne masque pas un mismatch de build |
| Terrain-RGB mal encodé si une source externe fournie par l'auteur ne respecte pas réellement la convention `terrarium` | Hors contrôle de GeoStudio (source externe) — documenté dans l'UI du `TerrainPanel` (texte d'aide citant la convention attendue), pas une garde côté serveur |
| `tileset.json` externe indisponible/CORS bloqué au chargement | Défaut déjà géré par deck.gl/loaders.gl (couche vide, pas de crash) ; comportement à vérifier en test manuel plutôt qu'en E2E (dépend d'un serveur tiers réel) |
| Persistance pitch/bearing régresse une carte 2D existante sans les champs | `pitch`/`bearing` optionnels des deux côtés (shell et Pydantic), défaut 0 — une carte existante sans ces champs se comporte exactement comme avant (`?? 0` partout) |
| Confusion entre le composant React `MapView` (shell) et le modèle Pydantic `MapView` (cœur), déjà homonymes avant ce document | Documenté explicitement en tête de ce spec (§0) et à chaque mention Pydantic dans ce document — pas un renommage (trop de sites d'usage existants pour un gain marginal) |
