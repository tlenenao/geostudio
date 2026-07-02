# GeoStudio SP-0c — Éditeur de carte (MapLibre + Deck.gl)

> Design / spec. Arc SP-0c du shell GeoStudio (après SP-0b). Livre l'éditeur de cartes :
> voir / créer / éditer / sauvegarder des « maps » (fond + couches + vue), avec des couches
> issues des services plateforme (Martin/TiTiler/pg_featureserv) et des overlays Deck.gl.
> Débloque le type d'item `map`.
>
> Date : 2026-07-02
> Statut : design validé — prêt pour `writing-plans`.
> Prérequis : SP-0a (Builder Service), SP-0b (shell : item-client, catalogue, ItemActions,
> NewItemButton) livrés.

---

## 1. Contexte et périmètre

SP-0b a livré le shell et la gestion d'items (apps/dashboards). SP-0c ajoute le **troisième
type d'item, la carte**, et son **éditeur complet** :

- **Visionneuse** `MapView` : rend une `MapConfig` (fond de carte + couches + vue) via
  MapLibre GL + overlay Deck.gl. Réutilisable en lecture et en édition.
- **Éditeur** : créer une map, ajouter des couches (picker sur les services plateforme),
  réordonner / masquer / retirer, choisir le fond, capturer l'emprise, **sauvegarder**.
- **Couches** : vecteur (Martin MVT), raster (TiTiler COG), features (pg_featureserv GeoJSON),
  et overlays **Deck.gl** (heatmap / hexbin / colonnes 3D).

**Hors périmètre :** édition de la donnée source (features) ; symbologie avancée (classes,
expressions) au-delà d'un style de base ; import de fichiers ; datasets GeoNode comme source
(on utilise les services plateforme) ; temps réel.

## 2. Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Premier jalon | **Éditeur de carte complet** (phasé, voir §9) |
| Persistance | **Builder Service `kind="map"`** + config `MapConfig` (les maps sont des items comme apps/dashboards) |
| Sources de couches | **Services plateforme** via un picker : Martin (vecteur), TiTiler (raster), pg_featureserv (features) |
| Deck.gl | **Inclus** (heatmap / hexbin / colonnes 3D) en overlay sur MapLibre |
| Tests | **Mock `maplibre-gl` + `@deck.gl/mapbox`** en unitaire (traduction config→API) ; **E2E Playwright** pour le rendu réel |

## 3. Modèle de données — `MapConfig`

Façade (isolé de la représentation Builder Service) :
```ts
export type MapView = { center: [number, number]; zoom: number };
export type BaseMap = { style: string }; // URL de style MapLibre ou pmtiles://…
export type MapLayer =
  | { id: string; title: string; visible: boolean; kind: "vector"; tilesUrl: string; sourceLayer: string; paint?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "raster"; tilesUrl: string; opacity?: number }
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "deck"; deckType: "heatmap" | "hexbin" | "column"; dataUrl: string; props?: Record<string, unknown> };
export type MapConfig = { basemap: BaseMap; view: MapView; layers: MapLayer[] };
```

**Builder Service (SP-0a) — extension** : `kind` gagne `"map"` ; `layout` devient optionnel
(`Layout | None`) ; ajout d'un champ `map: MapConfigModel | None`. Le contrat existant
(app/dashboard, `POST/GET/PUT /configs`, revisions, rollback, by-item, `ItemClient`) reste
inchangé — seulement des additions. Un item `map` est créé via le flux existant
(`POST /configs` → item GeoNode lié) et supprimé via `DELETE /configs/by-item/{itemId}`.

## 4. `item-client` — extensions

- Opts `createItemClient` : ajout de `martinUrl` et `featureservUrl` (depuis la config env
  `VITE_MARTIN_URL`, `VITE_FEATURESERV_URL`).
- `type LayerSource = { id: string; title: string; kind: "vector" | "feature"; service: "martin" | "featureserv"; sourceLayer?: string; tilesUrl?: string; url?: string }`.
- `listLayerSources(): Promise<LayerSource[]>` — agrège Martin `GET {martinUrl}/catalog`
  (sources vecteur) et pg_featureserv `GET {featureservUrl}/collections` (features) ; mappe
  vers `LayerSource`. (TiTiler/raster : ajouté ultérieurement via une source COG ; hors 0c
  initial mais le type `raster` existe dans `MapLayer`.)
- `getMapConfig(pk)` / `saveMapConfig(pk, config)` : lisent/écrivent la `MapConfig` d'un item
  map via `GET/PUT {builderUrl}/configs/by-item/{pk}` (réutilise l'endpoint by-item de SP-0b.2-c ;
  le corps de la config contient `kind: "map"` + `map: MapConfig`).
- `createMapItem({ title, owner })` : `POST /configs` avec `kind: "map"` et une `MapConfig`
  squelette (fond par défaut, vue France, `layers: []`).

Toutes les URLs des services sont isolées dans la façade et mockées en test.

## 5. Composants

- **`MapView({ config, onViewChange? })`** — instancie une carte MapLibre GL ; applique
  `basemap.style` ; pour chaque `MapLayer` visible, ajoute la source + la couche MapLibre
  correspondante (vector/raster/feature), dans l'ordre du tableau ; monte un overlay Deck.gl
  (`@deck.gl/mapbox` `MapboxOverlay`) pour les couches `kind: "deck"`. Contrôles : zoom,
  légende (liste des couches visibles). `onViewChange` remonte `{ center, zoom }` au déplacement.
  Réutilisable en lecture seule (visionneuse) et dans l'éditeur.
- **`LayerPicker({ onAdd })`** — liste les sources via `useLayerSources` (`listLayerSources`) ;
  cliquer une source appelle `onAdd(layer)` (construit le `MapLayer` correspondant).
- **`LayersPanel({ layers, onChange })`** — liste éditable des couches : réordonner (monter/
  descendre), basculer `visible`, retirer ; ouvre le `LayerPicker` pour ajouter.
- **`BasemapSelect({ value, onChange })`** — choix du fond parmi une petite liste prédéfinie.
- **`MapEditorPage({ pk })`** — charge la `MapConfig` (`getMapConfig`) → état local ; compose
  `MapView` (avec `onViewChange` → met à jour `view`) + `LayersPanel` + `BasemapSelect` +
  bouton **Enregistrer** (`saveMapConfig`) ; états loading/erreur ; alerte si save échoue.
- Intégration : `NewItemButton` gagne le type **Map** (crée `kind="map"` puis navigue vers
  l'éditeur) ; ouvrir une map depuis le catalogue/détail route vers `/maps/{pk}` (l'éditeur).

## 6. Hooks (TanStack Query)

- `useLayerSources()` → `useQuery(["layer-sources"], listLayerSources)`.
- `useMapConfig(pk)` → `useQuery(["map", pk], () => getMapConfig(pk))`.
- `useSaveMap(pk)` → `useMutation((config) => saveMapConfig(pk, config))` ; `onSuccess`
  invalide `["map", pk]`.
- `useCreateMap()` → `useMutation(createMapItem)` ; `onSuccess` invalide `["items"]`.

## 7. Flux de données

- **Créer** : NewItemButton (Map) → `useCreateMap` → `POST /configs` (kind map, config
  squelette) → navigue vers `/maps/{itemPk}`.
- **Éditer** : `MapEditorPage` charge `useMapConfig(pk)` → état local ; ajout de couche
  (LayerPicker → MapLayer), réordonner/masquer/retirer (LayersPanel), changer le fond, se
  déplacer (onViewChange met à jour la vue) → **Enregistrer** → `useSaveMap` PUT → invalide.
- **Rendu** : `MapView` traduit la `MapConfig` en sources/couches MapLibre + couches Deck.gl.

## 8. Gestion d'erreurs

- `MapView` : une couche dont la source échoue est isolée (log + omise) ; le reste de la carte
  rend. Style de fond invalide → fond par défaut.
- `getMapConfig`/`listLayerSources` en erreur → état d'erreur localisé + retry.
- Save échoué → toast/`role="alert"` ; l'éditeur reste ouvert, l'état local est préservé.
- 401/403 → géré par le shell.

## 9. Stratégie de tests (WebGL)

MapLibre GL et Deck.gl exigent un contexte WebGL absent de jsdom. Approche :
- **Unitaire (Vitest)** : `vi.mock("maplibre-gl")` et `vi.mock("@deck.gl/mapbox")` avec des
  doubles capturant les appels (`addSource`/`addLayer`/`setProps`/…). On teste :
  - `MapView` traduit une `MapConfig` en les bons appels (sources/couches attendues, ordre,
    visibilité, overlay Deck.gl pour les couches deck) ;
  - `LayersPanel` (add/reorder/remove/toggle) ; `LayerPicker` (MSW) ; `BasemapSelect` ;
  - `MapEditorPage` (charge, édite l'état, sauvegarde via le hook) ;
  - `item-client` `listLayerSources`/`getMapConfig`/`saveMapConfig`/`createMapItem` (MSW).
- **E2E (Playwright, Chromium a WebGL)** : créer une map → ajouter une couche → enregistrer →
  rouvrir et vérifier la couche ; le canvas MapLibre se monte réellement (assertion de présence
  du canvas + de la légende).
- **Backend (pytest)** : le Builder Service accepte/valide `kind="map"` + `map` (create, get,
  put by-item, round-trip de la MapConfig).

## 10. Phasage du plan d'implémentation

- **0c-a — Backend** (`builder-service/`) : `kind="map"`, `layout` optionnel, modèle `map`
  (MapConfig) ; validation + tests (create/get/put by-item, round-trip).
- **0c-b — `MapView` cœur** : MapLibre + fond + couches vector/raster/feature ; mock GL ; E2E
  smoke (canvas monté).
- **0c-c — Overlay Deck.gl** dans `MapView` (heatmap/hexbin/column).
- **0c-d — Sources & picker** : `item-client.listLayerSources` (Martin + pg_featureserv) +
  `useLayerSources` + `LayerPicker`.
- **0c-e — Éditeur & intégration** : `getMapConfig`/`saveMapConfig`/`createMapItem` + hooks +
  `LayersPanel`/`BasemapSelect`/`MapEditorPage` + route `/maps/:pk` + type Map dans
  `NewItemButton` + E2E create→add→save.

Chaque phase est testable seule ; `writing-plans` produira d'abord le plan de **0c-a**.

## 11. Dépendances

- Front : ajout de `maplibre-gl`, `@deck.gl/core`, `@deck.gl/layers`,
  `@deck.gl/aggregation-layers`, `@deck.gl/mapbox` (0c-b/0c-c).
- Backend : aucune nouvelle dépendance.

## 12. Contraintes globales

- Persistance des maps via Builder Service `kind="map"` ; le contrat existant reste inchangé
  (additions seulement).
- Front : tout accès réseau via `item-client` ; aucune URL de service en dur (config env) ;
  `Item`/`ItemClient` étendus sans rupture.
- MapLibre/Deck.gl mockés en unitaire ; le rendu réel n'est validé qu'en E2E.
- Une couche en erreur ne doit jamais faire échouer le rendu de la carte entière.
- Pas de token en localStorage (inchangé).
- Les endpoints Martin `/catalog` et pg_featureserv `/collections` sont best-effort (confinés
  à la façade, définis par les mocks) ; à ajuster contre les versions réelles.

### Notes différées (revue finale 0c-b)

- **Isolation par couche (spec §8)** : `applyLayers` n'entoure pas encore chaque couche d'un try/catch (MapLibre réel jette sur id dupliqué / spec invalide). À ajouter en 0c-e quand des couches réelles arrivent (log + couche omise, le reste rend).
- **`CreateKind`** : ajouter `"map"` en 0c-e (avec `createMapItem`).
- **Garde de rendu** : en 0c-e, préférer `map.isStyleLoaded()` à `map.loaded()` pour la garde d'application des couches (loaded() est false tant que des tuiles chargent).
- Naming `MapViewport` (vs spec `MapView`) et double-apply au montage (mock sync, inoffensif) : documentés, sans action.
