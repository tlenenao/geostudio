# SP-12e — Connecteurs GetCapabilities (WMS/WFS/WMTS) + affichage raster

- **Date** : 2026-07-23
- **Statut** : spec validée (brainstorm)
- **Prérequis** : SP-12c (moteur de moissonnage + connecteur STAC), SP-12d
  (connecteur ArcGIS FS + garde d'egress SSRF).
- **Suite** : SP-12f (CSW/ISO 19139), SP-12g (CKAN).

## 1. Contexte et objectif

SP-12 fédère des catalogues externes par moissonnage (référencement par défaut,
copie opt-in). Le moteur et deux connecteurs JSON existent : STAC (SP-12c) et
ArcGIS Feature Service (SP-12d), tous deux branchés sur le `HarvestConnector`
(protocole `fetch` → `HarvestedRecord`, plus `fetch_copy_geojson`) et sur la
garde d'egress SSRF.

SP-12e livre le connecteur ② de la feuille de route (A22) : **GetCapabilities
OGC**, décliné en trois services — **WMS**, **WFS**, **WMTS** — et satisfait le
critère d'acceptation « une couche WMS moissonnée s'affiche dans une carte sans
copie ». C'est le premier connecteur **XML** (STAC/ArcGIS étaient JSON).

L'incrément couvre donc, en un seul spec : les trois connecteurs **et**
l'affichage raster (WMS + WMTS forment une seule unité de rendu tuilé).

### Décisions de cadrage (brainstorm)

1. **Périmètre** : WMS + WFS + WMTS.
2. **Forme du registre** : trois types distincts `wms` / `wfs` / `wmts` (pas un
   seul type auto-détecté). `supports_copy` reste ainsi honnête par type.
3. **Frontière de l'incrément** : connecteurs **+ affichage raster** (WMS+WMTS)
   dans le même SP.
4. **Chemin d'ajout à la carte** : via le `LayerPicker` existant
   (`listLayerSources`), pas via une action « ajouter à la carte » du catalogue.
5. **Persistance du gabarit de tuiles** : colonnes sur `harvest_records` +
   jointure dans un endpoint dédié (pas de colonne générique sur `items`, pas de
   table dédiée).

## 2. Architecture

Trois connecteurs enregistrés séparément, conformes au `HarvestConnector`
existant, plus un module XML partagé et sûr. Le fil raster **réutilise** le rendu
`kind:"raster"` déjà présent dans `MapView` (`map.addSource(id, {type:"raster",
tiles:[tilesUrl], tileSize:256})`) — aucune nouvelle primitive cartographique.

```
core/app/harvest/connectors/
  base.py    ← existant : HarvestConnector, HarvestedRecord (+ champ ajouté)
  ows.py     ← NOUVEAU : parsing XML sûr + helpers namespace + bornes partagées
  wms.py     ← WmsConnector  (supports_copy=False) → raster_tiles_url
  wfs.py     ← WfsConnector  (supports_copy=True)  → items_url (copie GeoJSON)
  wmts.py    ← WmtsConnector (supports_copy=False) → raster_tiles_url
  __init__.py← _REGISTRY += wms / wfs / wmts
```

`defusedxml` = **nouvelle dépendance du cœur** (`core/pyproject.toml`). Elle
protège le parsing contre XXE et l'expansion d'entités (billion-laughs). Le
parsing est **tolérant et borné** au même titre que STAC/ArcGIS : un
GetCapabilities malformé, cyclique, géant ou hostile ne fait jamais tomber le
moissonnage ni ne bloque le worker — on journalise et on ignore, retour partiel.

### 2.1 Module `ows.py`

- `parse_capabilities(content: bytes) -> Element | None` : parse défensif via
  `defusedxml.ElementTree`, `None` sur échec (log warning).
- Helpers de navigation namespace-agnostiques (WMS 1.1.1 sans namespace vs
  1.3.0/WFS/WMTS avec namespaces `ows`, `wms`, `wfs`, `wmts`, `xlink`) : lookup
  par `local-name` plutôt que par QName figé.
- Bornes partagées : `_MAX_LAYERS`, `_MAX_DOCUMENTS`, timeout (10 s comme les
  autres), profondeur d'arbre WMS.

### 2.2 `HarvestedRecord`

Ajout d'un champ :

```python
@dataclass(frozen=True)
class HarvestedRecord:
    external_id: str
    title: str
    abstract: str
    keywords: list[str]
    bbox: list[float]
    external_url: str
    items_url: str | None          # copie vecteur (WFS/STAC/ArcGIS)
    raster_tiles_url: str | None = None   # NOUVEAU : gabarit tuiles (WMS/WMTS)
```

Un connecteur pose **soit** `items_url` (copiable), **soit** `raster_tiles_url`
(affichable en raster), jamais les deux dans SP-12e.

## 3. Les trois connecteurs

### 3.1 WMS (`WmsConnector`, `supports_copy = False`)

- `fetch(url)` : GET du GetCapabilities (client d'egress gardé), parse, parcourt
  l'arbre `<Layer>` (borné en profondeur et en nombre). Un `<Layer>` **nommé**
  (possède `<Name>`) devient un record ; les couches-groupes sans nom sont
  traversées mais pas émises.
- `title` = `<Title>` ou `<Name>` ; `abstract` = `<Abstract>` ; `keywords` =
  `<KeywordList>`.
- `bbox` : `<EX_GeographicBoundingBox>` (WMS 1.3.0) ou `<LatLonBoundingBox>`
  (1.1.1) ; défaut `_WORLD_BBOX` si absent/illisible.
- `external_url` = URL du GetCapabilities (endpoint du service).
- `raster_tiles_url` = gabarit **GetMap** en EPSG:3857 :
  `{base}?service=WMS&version=1.3.0&request=GetMap&layers={Name}&styles=&crs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256&format=image/png&transparent=true`.
  maplibre substitue `{bbox-epsg-3857}` par tuile. En demandant EPSG:3857 (axes
  x,y) on évite le piège d'ordre d'axes de WMS 1.3.0 en EPSG:4326.
- **Dégradation** : si le service n'annonce pas EPSG:3857 (ni alias 900913) pour
  la couche → `raster_tiles_url=None` (couche cataloguée mais non ajoutable).
- `fetch_copy_geojson` → `None` (raster, non copiable).

### 3.2 WFS (`WfsConnector`, `supports_copy = True`)

- `fetch(url)` : GET GetCapabilities, chaque `<FeatureType>` = un record.
- `title` = `<Title>` ou `<Name>` ; `bbox` = `<ows:WGS84BoundingBox>` (2.0.0) ou
  `<LatLongBoundingBox>` (1.1.0).
- `external_url` = endpoint du service.
- `items_url` = gabarit **GetFeature** GeoJSON :
  `{base}?service=WFS&version=2.0.0&request=GetFeature&typeNames={Name}&outputFormat=application/json&srsName=EPSG:4326`.
- `fetch_copy_geojson(record, http_get)` : pagine via `startIndex`/`count`
  (comme ArcGIS), **bornée** (nombre de pages et d'entités), retour d'une
  `FeatureCollection` GeoJSON. Tolérante : page malformée → arrêt propre.
- `raster_tiles_url` → `None`.

### 3.3 WMTS (`WmtsConnector`, `supports_copy = False`)

- `fetch(url)` : GET GetCapabilities, chaque `<Layer>` = un record.
- `bbox` = `<ows:WGS84BoundingBox>`.
- Recherche d'un `TileMatrixSet` Web Mercator (identifiants usuels
  `GoogleMapsCompatible`, `WebMercatorQuad`, ou CRS `EPSG:3857`/`urn:...:3857`).
- `raster_tiles_url` = gabarit `{z}/{y}/{x}` :
  - **ResourceURL** RESTful (`<ResourceURL format="image/png"
    resourceType="tile" template="...">`) si présent : on substitue
    `{TileMatrix}`→`{z}`, `{TileRow}`→`{y}`, `{TileCol}`→`{x}`, et la couche de
    style/dimension par défaut.
  - sinon gabarit **KVP GetTile**.
- **Dégradation** : pas de matrice Web Mercator, ou identifiants de TileMatrix
  non entiers (0..N incompatibles avec `{z}` maplibre) → `raster_tiles_url=None`.
- `fetch_copy_geojson` → `None`.

## 4. Persistance et API

### 4.1 Migration 0017

`harvest_records` gagne trois colonnes nullable :

| colonne        | type   | rôle                                            |
|----------------|--------|-------------------------------------------------|
| `external_url` | String | lien vers le service/la couche externe          |
| `tiles_url`    | String | gabarit de tuiles raster (null si non affichable)|
| `layer_kind`   | String | `"raster"` \| `"feature"` \| `null`             |

`service._upsert_reference` / `_upsert_copy` renseignent ces colonnes depuis le
`HarvestedRecord` (`raster_tiles_url` → `tiles_url`, `layer_kind="raster"` quand
`raster_tiles_url` est présent). `external_url` est désormais persisté pour tous
les types (aujourd'hui il était abandonné en mode référence).

### 4.2 Endpoint `GET /harvest/layers`

Nouvel endpoint dans le module harvest (`routes.py`) :

- Paramètre optionnel `q` (filtre titre).
- Renvoie les `harvest_records` où `tiles_url IS NOT NULL`, joints aux `items`
  pour le titre, **filtrés par tenant** et par la porte `can()` /
  publication/visibilité (mêmes règles que le catalogue).
- Forme JSON : `{ "layers": [ { "id", "title", "kind": "raster", "tilesUrl" } ] }`.

## 5. Shell

- `core/app/harvest/schemas.py` : `Literal["stac","arcgis"]` →
  `Literal["stac","arcgis","wms","wfs","wmts"]` (dans `HarvestSourceCreate`).
- `shell/src/api/types.ts` : `HarvestSourceType` += `"wms" | "wfs" | "wmts"` ;
  `core-schema.d.ts` régénéré depuis l'OpenAPI.
- `CreateHarvestSourceDialog.tsx` : trois `<option>` (WMS / WFS / WMTS) ; le mode
  **« copie » est désactivé** sauf pour `{stac, arcgis, wfs}` (grisé pour
  wms/wmts, qui sont référence-only).
- `LayerSource` : `kind` += `"raster"`, `service` += `"external"`.
- `LayerPicker.toMapLayer` : branche `raster` → `{ id, title, visible:true,
  kind:"raster", tilesUrl, opacity: 1 }`. `MapView` sait déjà rendre ce `kind`.
- `itemClient.listLayerSources` : 3ᵉ source dans le `Promise.allSettled` →
  `fetchExternalRasterSources(q)` sur `GET /harvest/layers`. La panne d'un
  service ne casse pas les autres (comportement déjà en place).

## 6. Erreurs et sécurité

- **SSRF** : tout HTTP serveur (fetch capabilities + pagination copie WFS) passe
  par le client d'egress gardé (`build_guarded_client` / `http_get` injecté),
  comme ArcGIS. `EgressBlockedError` remonte au moteur, non capturée par le
  connecteur.
- **XML** : `defusedxml` neutralise XXE et l'expansion d'entités. Bornes
  supplémentaires (nb de couches/feature types/documents, profondeur d'arbre
  WMS, timeout) contre un capabilities géant. Parsing tolérant : log-and-skip,
  retour partiel, jamais d'exception propagée hors du connecteur (le contrat
  harvest est de ne jamais lever, cf. SP-12c/d).
- **Tuiles raster** : récupérées **côté navigateur** (maplibre), pas de proxy
  serveur ; la garde d'egress ne s'y applique donc pas. Assumé pour des services
  **publics** uniquement (cohérent avec le résiduel ArcGIS v0).

## 7. Plan de tests

### Unitaires connecteurs (fixtures GetCapabilities capturées)

- WMS 1.3.0 **et** 1.1.1 → records, bbox, gabarit GetMap corrects ; couche-groupe
  sans nom non émise ; couche sans EPSG:3857 → `raster_tiles_url=None`.
- WFS 2.0.0 → records + gabarit GetFeature ; `fetch_copy_geojson` pagine et est
  borné ; page malformée → arrêt propre.
- WMTS → record + gabarit `{z}/{y}/{x}` (ResourceURL et KVP) ; sans matrice Web
  Mercator / identifiants non entiers → `raster_tiles_url=None`.
- Sécurité/robustesse : charge XXE/billion-laughs neutralisée ; capabilities
  malformé/géant → retour partiel, pas d'exception ; timeout respecté.

### Service / repository

- Persistance de `tiles_url` / `layer_kind` / `external_url` en référence et en
  copie (WFS).
- `GET /harvest/layers` : ne renvoie que `tiles_url IS NOT NULL`, filtre tenant +
  `can()` + `q`.

### Shell

- `CreateHarvestSourceDialog` : options WMS/WFS/WMTS ; gating du mode copie.
- `LayerPicker.toMapLayer` : mappe `raster` correctement.
- `itemClient.listLayerSources` : agrège la 3ᵉ source ; tolère sa panne.

### E2E Playwright (mock)

Parcours : admin crée une source **WMS** → moissonnage (mock) → item raster
externe → éditeur de carte → recherche dans le `LayerPicker` → ajout de la couche
→ assertion qu'une source `raster` est ajoutée à la carte. Miroir de l'E2E
SP-12d.

## 8. Découpage pour le plan (un seul spec, 4 phases)

1. **Connecteurs** : `ows.py` + `wms.py` + `wfs.py` + `wmts.py` + champ record
   (TDD, fixtures). Dépendance `defusedxml`.
2. **Persistance & API** : migration 0017, persistance service, endpoint
   `GET /harvest/layers`.
3. **Shell** : schémas, dialogue + gating copie, `LayerSource`/`toMapLayer`
   raster, agrégation `itemClient`.
4. **E2E + docs** : parcours Playwright, mise à jour `CLAUDE.md` / feuille de
   route (SP-12e livré, reste SP-12f/g).

## 9. Hypothèses v0 et résiduels documentés

- **Services publics** uniquement (pas de token/OAuth distant) — même résiduel
  qu'ArcGIS v0.
- **WMS** : suppose la disponibilité d'EPSG:3857 ; sinon la couche est
  cataloguée mais non ajoutable (référence-only).
- **WMTS** : n'ajoute à la carte que les couches offrant une matrice Web
  Mercator à identifiants entiers ; sinon référence-only.
- **Attribution / légende** des couches externes non modélisées en v0.
- **Pas de proxy de tuiles serveur** : le navigateur récupère les tuiles
  directement du service externe.
- Résiduel DNS-rebinding TOCTOU de la garde d'egress inchangé (pinning-IP
  toujours différé).

## 10. Hors périmètre

- CSW/ISO 19139 (SP-12f) et CKAN (SP-12g).
- Affichage **vecteur** d'une couche WFS sans copie (seule la copie WFS→GeoJSON
  est livrée ; le rendu vecteur direct d'un WFS distant est différé).
- Authentification vers des services protégés, proxy de tuiles, cache serveur.
