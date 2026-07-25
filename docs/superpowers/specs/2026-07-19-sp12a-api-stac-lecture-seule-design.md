# SP-12a — API STAC native (lecture seule) — design

**Date.** 2026-07-19
**Phase.** SP-12a, première sous-phase de SP-12 « Catalogue interopérable :
STAC, DCAT, moissonnage ».
**Références.** Feuille de route §SP-12 et arbitrage **A20** (routes STAC natives
dans le cœur, sur les tables `items`/`collections` existantes) ; A7 (STAC est le
bon habit pour les *données*, pas pour apps/dashboards).

## 1. Objectif & périmètre

**Objectif.** Le catalogue de données GeoStudio se lit avec le standard STAC :
un client STAC (QGIS plugin STAC, `pystac-client`, futurs consommateurs) navigue
le catalogue, liste les collections et cherche des items, en respectant les
permissions (le STAC anonyme n'expose que le publié/public).

**Dans le périmètre.**
- API STAC **native, lecture seule** dans le cœur (A20 option a), classes de
  conformité **core → collections → features → item-search**.
- Sur les tables/chemins existants : plateforme `Collection` → STAC Collection ;
  chaque feature → STAC Item (réutilise le chemin de requête OGC Features de
  SP-3b).
- Vérification de conformité par `stac-pydantic` dans la suite de tests
  (bloquant, offline) + smoke `stac-api-validator` documenté (non bloquant).

**Hors périmètre (sous-phases ultérieures de SP-12).**
- **SP-12b** : export **DCAT-AP** JSON-LD moissonnable (A21).
- **SP-12c…** : **moteur de moissonnage** (`harvest_sources`) + les 4 connecteurs
  (STAC externes → WMS/WFS GetCapabilities → CSW/ISO 19139 → CKAN, A22/A23),
  chacun un incrément autonome.
- **UI** : administration des sources, badge « externe » sur les items, ajout
  d'une couche moissonnée à une carte — rattachée au moissonnage.

**Cœur uniquement.** Aucune surface shell ni MCP. STAC est une API machine.
Le shell n'est pas touché → **les 38 specs E2E restent inchangées**.

## 2. Décisions de modélisation

### 2.1 Ce qu'est un STAC Item (arbitré)

STAC organise Catalog → Collections → Items. Le mapping retenu :

| STAC | GeoStudio |
|---|---|
| Catalog (landing) | Le catalogue du tenant courant |
| **Collection** | Une plateforme `Collection` (table de features enregistrée) |
| **Item** | Une **feature** (ligne) de cette collection |

Conséquence : item-search **réutilise le chemin de requête OGC Features de
SP-3b** (`app/features/repository.py` : `select_features`, `get_feature`, filtre
`bbox` déjà présent, `rls_scope`). Les apps/dashboards/maps (`items`) **ne sont
pas** exposés en STAC (A7 : STAC est le bon habit pour les données).

### 2.2 `datetime` des Items

Les features n'ont pas de dimension temporelle propre, or STAC exige qu'un Item
porte un `datetime` (ou un couple `start_datetime`/`end_datetime`). **v0 :** tout
Item porte le `updated_at` de sa collection.

- Simplification **documentée**. Raffinement futur possible : détecter une
  colonne temporelle du schéma de la collection.
- Le filtre `datetime` d'item-search opère donc à la **granularité collection** :
  une collection est « dans l'intervalle » ssi son `updated_at` l'est ; tous ses
  items le sont alors ou aucun.
- `datetime` est une **clé réservée** dans `properties` : la valeur synthétique
  écrase un éventuel attribut homonyme de la feature (documenté).

### 2.3 Emprise spatiale des Collections

STAC Collection exige une emprise spatiale. Calcul :
`ST_EstimatedExtent(schema, table, geom_col)` (rapide, via les stats `ANALYZE`)
avec repli `ST_Extent(...)` quand les stats sont absentes (résultat `NULL`),
**reprojeté en 4326**. Les emprises STAC étant *advisory*, l'approximation par
statistiques est assumée et documentée.

- Collection sans colonne géométrie ou table vide → emprise incalculable →
  **repli emprise monde** `[-180, -90, 180, 90]` avec note.
- Emprise temporelle de la Collection : `interval: [[created_at, null]]`
  (intervalle ouvert vers le futur).

### 2.4 `license`

Les `Collection` n'ont pas de champ licence. **v0 :** `license: "other"` en dur
(documenté), plutôt que d'omettre le champ. À raffiner si un champ licence est
ajouté au modèle de collection.

## 3. Nouveau module `core/app/stac/`

- **`serializers.py`** — fonctions **pures** construisant des dicts STAC
  (Catalog / Collection / Item / ItemCollection / conformance). Zéro I/O,
  testables en isolation. Les réponses sont construites à la main (pas de
  dépendance **runtime** à `stac-pydantic`, qui reste une dépendance de test).
- **`extent.py`** — `estimated_bbox_4326(session, info) -> list[float] | None`
  selon §2.3.
- **`routes.py`** — routeur `APIRouter` monté sous `/stac` dans `app.main`.

**Frontière de modules (import-linter).** `app.stac` peut importer
`app.collections`, `app.features`, `app.auth`, `app.db` ; jamais l'inverse.
Contrat ajouté au fichier import-linter (comme pour `app.extensions` en SP-8c).

## 4. Surface d'endpoints

Tous `GET`, lecture seule (plus `POST` sur `/search`). Préfixe `/stac` — pas de
collision avec les routes OGC Features existantes (`GET /`, `GET /collections/...`
à la racine).

| Endpoint | Rôle | Classe |
|---|---|---|
| `GET /stac` | Landing = Catalog : `id`, `type:"Catalog"`, `stac_version`, `conformsTo`, `links` (self, root, `data`→/stac/collections, `search`→/stac/search, `conformance`, `child` par collection) | Core |
| `GET /stac/conformance` | `{ "conformsTo": [ … ] }` | Core |
| `GET /stac/collections` | `{ "collections": [ … ], "links": [ … ] }` — STAC Collections visibles | Collections |
| `GET /stac/collections/{id}` | Une STAC Collection ; **404 non-fuyant** si non lisible | Collections |
| `GET /stac/collections/{id}/items` | ItemCollection (`limit`, `bbox`, lien `next`) | Features |
| `GET /stac/collections/{id}/items/{featureId}` | Un STAC Item | Features |
| `GET`/`POST /stac/search` | item-search cross-collections (`bbox`, `datetime`, `collections`, `ids`, `limit`, lien `next`) | Item Search |

**`conformsTo` annoncé** (`stac_version: "1.0.0"`) :
- `https://api.stacspec.org/v1.0.0/core`
- `https://api.stacspec.org/v1.0.0/collections`
- `https://api.stacspec.org/v1.0.0/ogcapi-features`
- `https://api.stacspec.org/v1.0.0/item-search`
- Les URIs OGC API Features Part 1 requis par la classe Features :
  `http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core`,
  `.../conf/oas30`, `.../conf/geojson`.

## 5. Objets STAC

### 5.1 STAC Collection ← plateforme `Collection`
`type: "Collection"`, `stac_version`, `id`, `title`, `description`,
`license: "other"` (§2.4), `extent` (§2.3), `links` (self, root, parent→landing,
`items`→.../items). Pas de `keywords` (les collections n'en ont pas).

### 5.2 STAC Item ← feature GeoJSON
`type: "Feature"`, `stac_version`, `id: featureId`, `collection: collectionId`,
`geometry` + `bbox` de la feature, `properties: { datetime: <collection.updated_at>,
…attributs }`, `assets: {}` (une feature n'est pas un asset téléchargeable —
objet vide, valide STAC), `links` (self, parent→collection, collection, root).

## 6. Permissions & visibilité (non négociable — réutilise l'existant)

- Portée de listing/search = `list_visible_collections(...)` ; collection unique
  + items = le chemin `get_readable_collection(...)` déjà éprouvé (SP-13b/c).
- **Anonyme → tenant `default` + publié/public seulement.** Collection non
  lisible → **404 non-fuyant** (convention SP-13, pas de fuite d'existence).
- Les lignes de features restent sous `rls_scope` (rôle `gis_rls` + GUC tenant,
  SP-3b) : les requêtes d'items STAC tournent sous la même portée.
- **Test adversarial dédié** : anonyme ne voit que le public, aucune fuite
  cross-tenant sur collections **et** items.

## 7. Pagination

- Items d'une collection : `limit` + `offset` via `select_features` ; lien `next`
  portant l'`offset` suivant tant qu'une page pleine est renvoyée.
- `/search` cross-collections : parcours des collections visibles (∩ filtre
  `collections`) dans un **ordre stable** ; token `next` = `{collectionId, offset}`
  encodé, reprenant au bon point. YAGNI mais honnête (pas de curseur global).

## 8. Tests & validation de conformité

- **Gate CI (bloquant, offline, always-run).** Les serializers purs validés
  contre les modèles **`stac-pydantic`** (Catalog / Collection / Item /
  ItemCollection) + assertion des URIs `conformsTo`. `stac-pydantic` ajouté en
  **dépendance de test** (`pyproject.toml`).
- **Intégration (marqueur `postgis`).** Seed d'une collection, chaque endpoint
  exercé : conformance, 404 non-fuyant, portée RLS anonyme, filtre `bbox`, lien
  `next`, search cross-collection, `datetime` à la granularité collection.
- **Smoke d'acceptation documenté (non bloquant).** `stac-api-validator` contre
  une instance vive seedée + navigation `pystac-client` / QGIS STAC — comme les
  validations empiriques de SP-10b/SP-11.

## 9. Dérive OpenAPI

Nouveaux endpoints → `core/openapi.json` et `shell/src/api/generated/
core-schema.d.ts` régénérés, même si le shell ne les appelle pas (le job
`api-types-drift` les verrait sinon diverger).

## 10. Critères d'acceptation (sous-ensemble SP-12a de SP-12)

1. `GET /stac` annonce core + collections + features + item-search ;
   `pystac-client`/QGIS STAC navigue le catalogue, liste collections et items.
2. Le STAC anonyme n'expose que le publié/public (test adversarial, sans fuite
   d'existence ni cross-tenant).
3. `stac-pydantic` valide tous les payloads dans la suite de tests ; le smoke
   `stac-api-validator` passe contre une instance vive (documenté).
4. item-search `bbox` + `collections` renvoie les bons STAC Items ; le lien
   `next` pagine ; `datetime` géré à la granularité collection.

## 11. Risques & simplifications assumées

- **`datetime` synthétique** (§2.2) : coarse, documenté, raffinable.
- **Emprise approximative** par `ST_EstimatedExtent` (§2.3) : *advisory* par
  nature en STAC.
- **`license: "other"`** en dur (§2.4) : à raffiner avec un champ licence.
- **Pagination `/search`** par token `{collectionId, offset}` sans curseur
  global : suffisant à l'échelle catalogue, pas de garantie de cohérence sous
  écritures concurrentes (lecture best-effort, acceptable pour un catalogue).
