# SP-12g — Connecteur CKAN / data.gouv.fr

- **Date** : 2026-07-24
- **Statut** : spec validée (brainstorm)
- **Prérequis** : SP-12c (moteur de moissonnage + connecteur STAC, référence
  de `supports_copy = True`), SP-12d (connecteur ArcGIS FS + garde d'egress
  SSRF), SP-12f (connecteurs CSW/OGC API - Records, dernier avant celui-ci).
- **Suite** : aucune — dernier connecteur d'A22 (les cinq).

## 1. Contexte et objectif

SP-12g livre le connecteur ⑤ et dernier de la feuille de route (A22) :
**CKAN/data.gouv.fr**. Ordre final : STAC → ArcGIS FS → GetCapabilities →
CSW/OGC API - Records → **CKAN**. La feuille de route positionne
volontairement ce connecteur en dernier (« métadonnées géo pauvres ») : un
paquet CKAN catalogue des jeux de données hétérogènes (CSV, GeoJSON, GPKG,
Shapefile zippé, PDF, tableurs...), pas garantis d'être une couche géo
exploitable — contrairement à STAC ou ArcGIS FS qui sont nativement
géospatiaux.

Malgré ce rationnel de fin de liste, le brainstorm a tranché que CKAN mérite
un **support de copie opt-in** (`supports_copy = True`), pas un
référencement pur comme CSW/OGC API - Records : de nombreux portails CKAN
(data.gouv.fr en tête) exposent des ressources directement téléchargeables
dans un format géo reconnu, et l'ingestion SP-6 sait déjà les avaler. Ce
choix a une conséquence architecturale directe (§4) : le pipeline de copie
partagé (`service.py::_upsert_copy`) est aujourd'hui figé sur un nom de
fichier codé en dur (`"harvest.geojson"`), parce que les deux connecteurs
`supports_copy = True` existants (STAC, ArcGIS) ne produisent que du GeoJSON.
CKAN casse cette hypothèse.

### Décisions de cadrage (brainstorm)

1. **Découverte** : API Action CKAN `package_search` (`/api/3/action/
   package_search`), paginée par `start`/`rows` — pas de `package_show` en
   N+1, `package_search` retourne déjà les paquets complets.
2. **Filtrage** : pas de nouveau champ dans le dialogue d'ajout de source.
   L'admin peut encoder des paramètres CKAN (`q`, `fq`, `tags`,
   `organization`...) directement dans l'URL fournie ; le connecteur les
   transmet tels quels à `package_search`, fusionnés proprement avec la
   pagination (pas de concaténation de chaîne façon `csw.py::_page_url`).
3. **Copie** : `supports_copy = True`, mais **extension minimale** plutôt
   qu'un renommage du protocole `HarvestConnector` (§4) — `HarvestedRecord`
   gagne un champ optionnel `copy_filename`, `service.py` l'utilise à la
   place du littéral codé en dur. Zéro changement pour les 6 autres
   connecteurs (défaut `None` → comportement identique à aujourd'hui).
4. **Formats copiables v1** : GeoJSON, GPKG, Shapefile zippé — dans cet
   ordre de préférence si un paquet expose plusieurs resources géo. **CSV
   exclu de la copie** (nécessiterait un mapping de colonnes lat/lon que
   `service.py` ne fournit pas pour la copie moissonnée — `lat_field`/
   `lon_field` sont passés à `None`). Un paquet sans resource géo reconnue
   reste moissonné en **référencement pur** (comportement de repli déjà
   existant : `items_url = None` → « sans contenu copiable », pas une
   nouvelle branche).
5. **Bbox** : extra `spatial` (GeoJSON, convention `ckanext-spatial`
   répandue sur les portails CKAN français dont data.gouv.fr) si présent et
   valide, sinon bbox monde — même tolérance que `StacConnector`.

## 2. Architecture

```
core/app/harvest/connectors/
  base.py   ← HarvestedRecord += copy_filename: str | None = None
  ckan.py   ← NOUVEAU : CkanConnector (package_search JSON REST paginé)
  __init__.py ← _REGISTRY += ckan
```

```
core/app/harvest/service.py
  _upsert_copy() : filename = rec.copy_filename or "harvest.geojson"
                   (remplace le littéral "harvest.geojson" codé en dur)
```

Aucune nouvelle colonne `harvest_records` (les colonnes existantes
`external_url`/`tiles_url`/`layer_kind` suffisent ; `tiles_url`/`layer_kind`
restent `NULL` pour CKAN, pas de couche raster). **Aucune migration
Alembic dans SP-12g.**

## 3. Connecteur CKAN (`CkanConnector`, `supports_copy = True`)

### 3.1 Fetch : `package_search` paginé

L'admin fournit l'URL du portail (racine, avec ou sans query CKAN déjà
encodée) :

```
GET {scheme}://{netloc}/api/3/action/package_search
    ?{params admin fusionnés}&start={n}&rows=100
```

- Découpage de l'URL admin via `urlsplit` : `scheme`/`netloc` retenus pour
  construire l'endpoint `package_search` ; les paires `query` existantes
  (`parse_qsl`) sont conservées et réinjectées à chaque page via `urlencode`,
  avec `start`/`rows` ajoutés/écrasés (jamais dupliqués, contrairement au
  souci mineur connu de `csw.py`).
- Bornes : `_MAX_CKAN_DATASETS = 500` (total émis), `_MAX_CKAN_PAGES = 50`,
  page size `rows=100`, timeout 10 s par requête.
- Client gardé (`build_guarded_client`), construit en interne comme les 6
  autres connecteurs.
- Arrêt propre : `result.count` épuisé, page vide, ou une des bornes
  atteinte. Toute page qui échoue (HTTP/JSON invalide) arrête la pagination
  en conservant les paquets déjà accumulés (retour partiel, même philosophie
  que STAC/CSW/OGC API - Records) — jamais d'exception qui fuite hors du
  connecteur.

### 3.2 Extraction des champs

Par paquet CKAN (`result.results[]`) :
- `external_id` = `pkg["id"]`.
- `title` = `pkg.get("title") or pkg["name"]`.
- `abstract` = `pkg.get("notes") or ""`.
- `keywords` = noms des `pkg.get("tags", [])` (`[t["name"] for t in tags si
  dict et "name" présent]`).
- `bbox` : cherche un extra `{"key": "spatial", "value": <geojson str>}`
  dans `pkg.get("extras", [])`, parse le JSON, calcule l'enveloppe si
  Polygon/bbox reconnu ; toute erreur (extra absent, JSON invalide,
  géométrie non reconnue) → bbox monde `[-180, -90, 180, 90]`, jamais
  d'exception.
- `external_url` = `{scheme}://{netloc}/dataset/{pkg.get("name") or
  pkg["id"]}`.
- `items_url`/`copy_filename` : voir §3.3.
- `raster_tiles_url = None` toujours.
- Un paquet sans `id` est ignoré (même discipline que CSW/OGC API -
  Records : pas d'upsert idempotent possible sans identifiant stable).

### 3.3 Sélection de la resource copiable

Pour chaque paquet, parcourt `pkg.get("resources", [])` et retient la
**première** resource dont le champ `format` (normalisé
`upper().strip()`) correspond à un format reconnu, par ordre de préférence :

| Format CKAN (`resource["format"]`) | `copy_filename` |
|---|---|
| `GEOJSON` | `harvest.geojson` |
| `GPKG` / `GEOPACKAGE` | `harvest.gpkg` |
| `SHP` / `SHAPEFILE` (zippé, format CKAN usuel) | `harvest.zip` |

Si une resource correspond : `items_url = resource["url"]`,
`copy_filename` défini selon le tableau. Si `resource["url"]` est absent/vide
ou aucune resource ne correspond : `items_url = None`, `copy_filename =
None` — le paquet reste moissonné (métadonnées upsertées) mais en
référencement, exactement comme le cas « sans lien items » déjà géré par
`service.py::_upsert_copy`.

### 3.4 Copie (`fetch_copy_geojson`)

```python
def fetch_copy_geojson(self, record, *, http_get):
    if record.items_url is None:
        return None
    return http_get(record.items_url).content
```

Identique au pattern STAC/ArcGIS — pas de renommage de méthode malgré le nom
historique « geojson » : son contrat réel est « bytes de la resource
choisie », le format effectif est porté par `record.copy_filename` et
interprété en aval par `service.py`/`_pick_format` (`importer.py`).

## 4. Extension du pipeline de copie partagé

`service.py::_upsert_copy` construit aujourd'hui :

```python
result = run_import(
    session, ..., filename="harvest.geojson", content=content, ...
)
```

Changement (1 ligne) :

```python
result = run_import(
    session, ..., filename=rec.copy_filename or "harvest.geojson", content=content, ...
)
```

`HarvestedRecord` (dataclass frozen, `base.py`) gagne :

```python
copy_filename: str | None = None
```

Pour les 6 connecteurs existants (STAC, ArcGIS, CSW, OGC API - Records, WMS,
WFS, WMTS), ce champ n'est jamais renseigné → défaut `None` →
`"harvest.geojson"` conservé tel quel. **Comportement strictement inchangé
pour STAC/ArcGIS** (seuls connecteurs `supports_copy = True` existants).
Zéro migration (le champ vit dans le dataclass Python, pas en base — la
table `harvest_records` ne stocke pas le nom de fichier de copie).

## 5. Sécurité

- **SSRF** : `package_search` passe par `build_guarded_client`, comme les 6
  autres connecteurs. La copie (`fetch_copy_geojson` → `http_get`) utilise le
  `http_get` injecté par le moteur (`egress.guarded_get` en prod) — jamais un
  client construit en dehors de la garde.
- **JSON** : type-checking défensif de chaque paquet/resource/extra avant
  extraction (même garde-fous que STAC/OGC API - Records) ;
  `(httpx.HTTPError, ValueError)` capturés localement, jamais remontés hors
  du connecteur.
- **Résidu partagé** : DNS-rebinding TOCTOU de la garde d'egress inchangé
  (pinning-IP toujours différé, résiduel documenté depuis SP-12d).

## 6. Plan de tests

### Unitaires connecteur (fixtures `package_search` JSON)

- Une page → records avec title/abstract/keywords/bbox/external_url
  corrects.
- Pagination multi-pages (`start`/`rows`) ; plafond `_MAX_CKAN_DATASETS`/
  `_MAX_CKAN_PAGES` tronque proprement.
- Fusion de query params : une URL admin avec `?organization=x&tags=geo`
  produit une requête `package_search` qui conserve `organization`/`tags`
  ET ajoute `start`/`rows`, sans doublon ni perte.
- Bbox : extra `spatial` valide → enveloppe correcte ; absent → bbox monde ;
  JSON malformé dans l'extra → bbox monde (pas d'exception).
- Sélection de resource copiable : GeoJSON présent → `items_url`/
  `copy_filename="harvest.geojson"` ; GPKG seul → `harvest.gpkg` ; SHP zippé
  seul → `harvest.zip` ; CSV seul (aucun format reconnu) → `items_url=None`,
  `copy_filename=None` ; plusieurs formats reconnus → priorité GeoJSON >
  GPKG > SHP respectée.
- Tolérance : paquet non-dict, `resources`/`tags`/`extras` non-liste, page
  JSON invalide, `result` absent → jamais d'exception, paquet ignoré ou
  page arrêtée proprement (résultat partiel conservé).
- Paquet sans `id` → ignoré.

### `fetch_copy_geojson`

- `items_url` présent → `http_get` appelé avec cette URL, contenu retourné
  tel quel.
- `items_url = None` → retourne `None` sans appel HTTP.

### Service (`_upsert_copy`)

- `copy_filename` porté par le record → `run_import` reçoit ce nom de
  fichier (test avec un fake connecteur CKAN-like renvoyant
  `copy_filename="harvest.gpkg"`).
- `copy_filename = None` (cas STAC/ArcGIS existants, régression) →
  `run_import` reçoit toujours `"harvest.geojson"`.

### Shell

- `CreateHarvestSourceDialog` : option CKAN présente, **mode copie
  disponible** (CKAN ajouté à `COPY_TYPES`, contrairement à CSW/OGC
  API - Records).
- `HarvestSourceType` (`core-schema.d.ts` régénéré + `types.ts`) inclut
  `"ckan"`.

### E2E Playwright (mock)

- **Référencement** : admin crée une source CKAN → moissonnage (mock
  `package_search`, paquet sans resource géo reconnue) → item « référence
  externe » cherchable au catalogue.
- **Copie** : admin crée une source CKAN en mode copie → moissonnage (mock
  `package_search` avec une resource GeoJSON + mock du contenu de la
  resource) → collection importée (SP-6) cherchable, avec ses features.

## 7. Découpage pour le plan

1. **`base.py`** : ajout `copy_filename` (TDD — test que le défaut `None`
   ne casse aucun connecteur existant).
2. **`service.py`** : `filename = rec.copy_filename or "harvest.geojson"`
   (TDD — régression STAC/ArcGIS + nouveau cas `copy_filename` renseigné).
3. **Connecteur CKAN** : `ckan.py` (TDD, fixtures `package_search`),
   `_REGISTRY += ckan`, `schemas.py` : `Literal[...] += "ckan"`.
4. **Shell** : `types.ts` + `core-schema.d.ts` régénéré ;
   `CreateHarvestSourceDialog` (nouvelle option + `COPY_TYPES += "ckan"`).
5. **E2E + docs** : 2 specs Playwright (référencement + copie) ; mise à
   jour `CLAUDE.md` (SP-12g livré, A22 les cinq connecteurs complets) et
   feuille de route (§ Connecteurs, table A22, jalon M9 le cas échéant).

## 8. Hors périmètre

- Copie CSV (nécessiterait un mapping de colonnes lat/lon configurable pour
  la copie moissonnée — hors périmètre v1, cf. décision de cadrage 4).
- Formats géo additionnels au-delà de GeoJSON/GPKG/SHP zippé (ex. KML,
  TopoJSON) — extensible plus tard via le même tableau de correspondance
  format→`copy_filename`, sans changement structurel.
- `package_show` par identifiant (recherche ciblée d'un seul paquet) —
  `package_search` paginé suffit au moissonnage plein-catalogue borné.
- Filtrage avancé exposé dans le dialogue (l'admin encode `q`/`fq` dans
  l'URL lui-même, pas de nouveau champ UI, cf. décision de cadrage 2).
- Endpoints CKAN authentifiés (`api_key`).
- Mise à jour du contenu déjà copié (même limite v0 que STAC/ArcGIS,
  documentée dans `service.py::_upsert_copy`).

## 9. Hypothèses v0 et résiduels documentés

- **Services publics** uniquement (pas de `api_key` distant) — même
  résiduel que les 4 connecteurs précédents.
- **Bbox** dépend de la convention `ckanext-spatial` (extra `spatial`) ;
  un portail CKAN qui expose l'étendue spatiale autrement (champ dédié
  non standard) tombe sur le bbox monde.
- Résiduel DNS-rebinding TOCTOU de la garde d'egress inchangé (pinning-IP
  toujours différé).
- **A22 (les cinq connecteurs) complet après SP-12g** — clôt l'arbitrage de
  la feuille de route ; tout connecteur additionnel futur (ex. GeoNetwork
  spécifique, ODS/Opendatasoft) serait un nouvel arbitrage, pas une suite
  implicite.
