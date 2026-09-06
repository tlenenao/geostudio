# SP-56 — Import : formats manquants (XLSX, KML/KMZ, GeoParquet) : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer GAP-09/GAP-29 (chantier 4.14) : ajouter XLSX, KML/KMZ et
GeoParquet en import, en étendant le pipeline `procrastinate` existant
(SP-6) — jamais en le dupliquant.

**Architecture:** 6 tâches, une par brique (3 parseurs, 1 intégration, 1
extension d'inspection, 1 frontend), dans l'ordre où chacune peut être
falsifiée indépendamment avant que la suivante n'en dépende.

**Tech Stack:** Python/FastAPI + `pyogrio`/`geopandas`/`openpyxl` + pytest
(cœur), TypeScript/React + Vitest + Playwright (shell). **Aucune nouvelle
dépendance** (`pyogrio`, `geopandas`, `pyarrow`, `openpyxl` sont déjà dans
`core/pyproject.toml`, vérifié).

**Document source :**
`docs/superpowers/specs/2026-09-05-sp56-import-formats-design.md` (§1 XLSX,
§2 KML/KMZ, §3 GeoParquet, §4 points communs, §6 critères de sortie).

## Global Constraints

- **Aucune dépendance sur SP-43.**
- **TDD / filet-avant-code** systématique.
- Commits **conventional**, français (`feat(core): ...`, `test(core): ...`,
  `feat(shell): ...`).
- **Suite complète rejouée avant de clore chaque tâche** : `cd core && uv
  run pytest`, et pour la Tâche 6, `cd shell && npm run test` + `npm run e2e`.
- **Tout filet de test ajouté doit être vérifié par falsification** (piège
  CLAUDE.md n°10).
- **Régénérer la spec OpenAPI + types TS** (piège CLAUDE.md n°1) : la
  Tâche 5 change la forme de `InspectResponse` — diff **non vide** attendu
  à cette tâche ; les Tâches 1-4 ne touchent aucune route/schéma de réponse,
  diff **vide** attendu (et légitime) si la commande est lancée par erreur.
- **Vérifier chaque affirmation contre le code réel avant de la coder** —
  en particulier le fait, déjà vérifié par exécution réelle avant
  d'écrire ce plan (spec §Contexte), qu'un `.kmz` se lit **sans**
  `/vsizip/` contrairement à `.zip` (Shapefile) : ne pas recopier le
  patron `.zip` par réflexe à la Tâche 2.
- **Piège CLAUDE.md n°4 (revue de branche)** : à la clôture, vérifier que
  les 4 formats déjà supportés (GeoJSON/CSV/GPKG/Shapefile) fonctionnent
  toujours après le passage de l'`if/elif` de `_pick_format`/`run_import`
  d'une chaîne à 4 branches à une chaîne à 7 — pas seulement les 3
  nouveaux formats testés isolément.

---

## Task 1 : parseur XLSX (`parse_xlsx_latlon`)

**Files:**
- Modify: `core/app/ingestion/parsers.py`
- Test: `core/tests/test_ingestion_parsers.py`

**Interfaces:**
- Consumes: `openpyxl.load_workbook`, `detect_lat_lon_fields` (déjà défini
  dans ce fichier, réutilisé tel quel).
- Produces: `parse_xlsx_latlon(content: bytes, lat_field: str | None,
  lon_field: str | None) -> Iterator[tuple[BaseGeometry, dict]]`.

- [ ] **Step 1 : écrire les tests (avant le code)**

Dans `core/tests/test_ingestion_parsers.py`, à côté des tests
`parse_csv_latlon` (lignes 67-94, patron à suivre pour la forme des
assertions) : construire un classeur XLSX en mémoire avec `openpyxl`
directement dans le test (`Workbook()`, `ws.append([...])`,
`wb.save(buf)`), pas de fixture binaire commitée. Cas à couvrir :
- auto-détection des colonnes lat/lon (en-têtes `lat`/`lon`) ;
- `lat_field`/`lon_field` explicites quand les en-têtes ne matchent pas ;
- échec rapide sur une ligne avec une valeur non numérique en lat/lon ;
- une cellule de type `datetime` dans une colonne propriété (pas lat/lon)
  est sérialisée en chaîne ISO 8601 dans les `properties` retournées —
  **c'est le cas qui n'a pas d'équivalent CSV**, à écrire explicitement
  avec une assertion sur le type ET la valeur de la propriété résultante ;
- une cellule vide → `None` en propriété (comme GeoJSON/GPKG).

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k xlsx -v
# attendu : ÉCHEC (fonction inexistante)
```

- [ ] **Step 2 : implémenter**

`parse_xlsx_latlon` (spec §1.2) : `load_workbook(BytesIO(content),
read_only=True, data_only=True)`, `wb.active`, en-tête = première ligne,
détection lat/lon (réutilise `detect_lat_lon_fields`), itération des
lignes suivantes, coercition `datetime`/`date` → `isoformat()` sur toute
valeur de propriété (pas seulement lat/lon).

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k xlsx -v
```

- [ ] **Step 3 : falsifier le filet de coercition datetime**

Retirer temporairement la coercition, confirmer que le test dédié échoue
(assertion sur le type `str` de la propriété, pas `datetime`), remettre.

- [ ] **Step 4 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute le parseur d'import XLSX (lat/lon)

Ferme GAP-09 pour XLSX (chantier 4.14) : même contrat que
parse_csv_latlon, avec coercition datetime -> isoformat() (openpyxl
rend des types Python natifs par cellule, contrairement au CSV où
tout est déjà une chaîne).
EOF
)"
```

---

## Task 2 : parseur KML/KMZ

**Files:**
- Modify: `core/app/ingestion/parsers.py` (`list_layers`, nouvelle fonction
  `parse_kml`)
- Test: `core/tests/test_ingestion_parsers.py`

**Interfaces:**
- Consumes: `_read_features` (déjà générique, réutilisé sans modification),
  `_temp_file`.
- Produces: `parse_kml(content: bytes, layer_name: str | None = None) ->
  Iterator[...]`, `list_layers` étendu aux extensions `.kml`/`.kmz`.

- [ ] **Step 1 : écrire les tests (avant le code)**

À côté des tests GPKG (lignes 230-343, patron à suivre) : construire un
`.kml` minimal en mémoire (une chaîne XML avec un `<Placemark><Point>`,
comme vérifié à la main lors de l'écriture de la spec — réutiliser le même
gabarit XML), et un `.kmz` (zip contenant ce même contenu sous
`doc.kml`, via `zipfile.ZipFile` en mémoire). Cas à couvrir :
- `parse_kml` sur un `.kml` à une seule couche : géométrie + propriétés
  correctes ;
- `parse_kml` sur un `.kmz` : **même résultat**, sans passer par
  `/vsizip/` (le test doit passer le contenu du `.kmz` tel quel, sans
  wrapper — s'assurer que le test échouerait si le code ajoutait par
  erreur un préfixe `/vsizip/` sur ce chemin, en construisant un `.kmz`
  qui échouerait silencieusement ou bruyamment sous ce préfixe erroné,
  au jugement de l'exécutant) ;
- `list_layers()` sur `.kml`/`.kmz` retourne les couches attendues (même
  forme que les tests GPKG existants, lignes 182-220) ;
- fichier KML corrompu → `IngestionParseError` (même patron que
  `test_parse_gpkg_rejects_unknown_layer_name` / `test_list_layers_corrupted_file_raises_parse_error`).

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "kml or kmz" -v
```

- [ ] **Step 2 : implémenter**

`parse_kml` (spec §2.1) et l'extension de `list_layers()` (branche
`.kml`/`.kmz`, `wrap = lambda p: p` — **ne pas** copier le `wrap` de la
branche `.zip` existante).

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -v
```

- [ ] **Step 3 : falsifier le choix "pas de `/vsizip/`"**

Modifier temporairement `parse_kml`/`list_layers` pour préfixer
`/vsizip/` sur le chemin `.kmz` (comme le fait `parse_shapefile_zip`),
confirmer que le test `.kmz` échoue (ou lève une erreur GDAL), remettre.
C'est la preuve que ce détail, contre-intuitif par rapport au traitement
`.zip` existant, est réellement nécessaire et pas une supposition non
vérifiée.

- [ ] **Step 4 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute l'import KML/KMZ

Ferme GAP-09 pour KML/KMZ (chantier 4.14) : réutilise _read_features
tel quel (GDAL/pyogrio lit KML nativement, driver LIBKML, aucune
dépendance nouvelle) ; .kmz se lit directement, sans le préfixe
/vsizip/ qu'exige .zip (Shapefile) — vérifié par falsification.
EOF
)"
```

---

## Task 3 : parseur GeoParquet

**Files:**
- Modify: `core/app/ingestion/parsers.py` (ou nouveau
  `core/app/ingestion/geoparquet.py`, au jugement de l'exécutant selon la
  taille du fichier à ce moment)
- Test: `core/tests/test_ingestion_parsers.py` (ou fichier jumeau si module
  séparé)

**Interfaces:**
- Consumes: `geopandas.read_parquet`, `_native_value` (réutilisé tel quel).
- Produces: `parse_geoparquet(content: bytes) -> Iterator[...]`.

- [ ] **Step 1 : écrire les tests (avant le code)**

Construire un GeoParquet en mémoire avec `geopandas`/`shapely`
directement dans le test (`gpd.GeoDataFrame(..., geometry=[...],
crs="EPSG:4326").to_parquet(path)` — même bibliothèque que la production
qui l'écrit réellement, `core/app/cdc/parquet_writer.py`, donc un test
réaliste plutôt qu'un fichier binaire commité). Cas à couvrir :
- lecture correcte géométrie + attributs ;
- CRS non-4326 dans le fichier source → reprojection automatique (vérifier
  avec un CRS métrique connu, ex. EPSG:2154 Lambert-93, cohérent avec des
  données françaises) ;
- une géométrie nulle dans une ligne → `IngestionParseError` ;
- **aller-retour réel avec `write_geoparquet`** (`core/app/cdc/parquet_writer.py`)
  : écrire avec la fonction de production existante, relire avec
  `parse_geoparquet`, vérifier que le résultat correspond — preuve directe
  du critère de sortie « le format déjà produit par le CDC devient
  consommable en import ».

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k parquet -v
```

- [ ] **Step 2 : implémenter**

`parse_geoparquet` (spec §3.1).

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -v
```

- [ ] **Step 3 : falsifier la reprojection CRS**

Retirer temporairement le `gdf.to_crs(epsg=4326)`, confirmer que le test
CRS non-4326 échoue (coordonnées hors plage WGS84 plausible), remettre.

- [ ] **Step 4 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute l'import GeoParquet

Ferme GAP-09 pour GeoParquet (chantier 4.14) : geopandas.read_parquet
(pyogrio n'a pas de driver Parquet dans ce build, vérifié), reprojection
vers 4326, aller-retour testé contre write_geoparquet (SP-11) — preuve
directe que le format déjà produit par le CDC est maintenant
consommable en import.
EOF
)"
```

---

## Task 4 : intégration `importer.py` (dispatch des 3 nouveaux formats)

**Files:**
- Modify: `core/app/ingestion/importer.py` (`_pick_format`, `run_import`)
- Test: `core/tests/test_ingestion_importer.py`

**Interfaces:**
- Consumes: les 3 parseurs des Tâches 1-3.
- Produces: `run_import(...)` accepte `.xlsx`/`.kml`/`.kmz`/`.parquet` en
  plus des 4 formats existants, produit une `Collection` + un `Item`
  identiques en forme à ceux produits par les formats existants.

- [ ] **Step 1 : écrire les tests d'intégration bout en bout (avant le code)**

Dans `core/tests/test_ingestion_importer.py`, à côté des tests existants
(patron à confirmer par lecture du fichier avant d'écrire) : un test par
nouveau format, qui appelle `run_import(session, ..., filename="x.xlsx",
content=<xlsx réel>, ...)` et vérifie la `Collection` créée (feature_count,
geometry_type) et l'`Item`/`Config` (`kind="map"`, une couche `feature`
pointant vers `/collections/{id}/items` — même forme que
`test_ingestion_importer.py` existant pour GeoJSON/CSV/GPKG). Un test qui
vérifie que `_pick_format` lève toujours `IngestionParseError` pour une
extension non reconnue (`.txt` par ex.) — non-régression du comportement
par défaut.

**Non-régression explicite (piège CLAUDE.md n°4)** : relancer les tests
existants GeoJSON/CSV/GPKG/Shapefile de ce même fichier sans aucune
modification, confirmer qu'ils passent toujours **avant** de commencer
l'implémentation (baseline), puis à nouveau **après** (pas de régression
introduite par le passage d'un `if/elif` à 4 branches à un à 7).

```bash
cd core && uv run pytest tests/test_ingestion_importer.py -v  # baseline, tout doit déjà passer
cd core && uv run pytest tests/test_ingestion_importer.py -k "xlsx or kml or kmz or parquet" -v
# attendu : ÉCHEC sur les nouveaux tests seulement
```

- [ ] **Step 2 : implémenter**

`_pick_format` : ajouter les 4 nouvelles extensions (`.xlsx`→`"xlsx"`,
`.kml`/`.kmz`→`"kml"`, `.parquet`→`"geoparquet"`). `run_import` :
restructurer le dispatch en `if/elif` explicite pour les 7 formats (plus de
`else` implicite qui suppose Shapefile — spec §4, transformer le dernier
`else: rows = list(parse_shapefile_zip(...))` en
`elif fmt == "shapefile": ...` explicite, avec un `else` final défensif
qui ne devrait jamais s'atteindre vu la garde de `_pick_format`).

```bash
cd core && uv run pytest tests/test_ingestion_importer.py -v
```

- [ ] **Step 3 : suite complète du module + commit**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py tests/test_ingestion_importer.py tests/test_ingestion_importer_perf.py -v
git add core/app/ingestion/importer.py core/tests/test_ingestion_importer.py
git commit -m "$(cat <<'EOF'
feat(core): intègre XLSX/KML/KMZ/GeoParquet au dispatch d'import

Ferme GAP-09 côté intégration (chantier 4.14) : _pick_format et
run_import couvrent maintenant 7 formats, dispatch explicite (plus de
else implicite supposant Shapefile) ; non-régression vérifiée sur les
4 formats existants avant/après.
EOF
)"
```

---

## Task 5 : `POST /uploads/inspect` étendu (champs XLSX + couches KML/KMZ)

**Files:**
- Modify: `core/app/ingestion/schemas.py` (`InspectResponse.fields`),
  `core/app/ingestion/routes.py::inspect_upload`
- Test: `core/tests/test_ingestion_routes.py`

**Interfaces:**
- Consumes: `parse_kml`/`list_layers` (Tâche 2), un lecteur d'en-tête XLSX
  léger (nouvelle petite fonction, ou réutilisation partielle de
  `parse_xlsx_latlon` limitée à la première ligne — au choix de
  l'exécutant, en évitant de charger tout le classeur juste pour
  l'inspection).
- Produces: `InspectResponse.fields: list[str] | None = None`, peuplé pour
  `.xlsx` ; `InspectResponse.layers` continue de fonctionner pour
  `.gpkg`/`.zip`/`.kml`/`.kmz` (déjà branché par `list_layers` étendu en
  Tâche 2 pour KML/KMZ — vérifier qu'aucun changement supplémentaire n'est
  nécessaire ici, seulement un test de non-régression).

- [ ] **Step 1 : écrire les tests (avant le code)**

`test_ingestion_routes.py` : un test `POST /uploads/inspect` avec un
`.xlsx` retourne `fields` (liste des en-têtes de la première ligne),
`layers` vide/absent. Un test avec un `.kml`/`.kmz` multi-couches retourne
`layers` (comme GPKG aujourd'hui), `fields` vide/absent. Un test `.parquet`
: **aucun changement de comportement attendu** — `list_layers()` ne doit
**pas** recevoir de branche `.parquet` (spec §3.1) ; vérifier que
`inspect_upload` sur un `.parquet` retourne l'erreur `ValueError`/HTTP 400
« format non concerné par l'inspection », comme GeoJSON/CSV aujourd'hui —
ce test protège contre l'ajout accidentel d'une inspection inutile pour ce
format.

```bash
cd core && uv run pytest tests/test_ingestion_routes.py -k "xlsx or parquet" -v
```

- [ ] **Step 2 : implémenter**

`InspectResponse` gagne `fields: list[str] | None = None`. `inspect_upload`
(ou `list_layers`, au choix — documenter lequel des deux porte la
distinction "layers vs fields" selon le format) : branche `.xlsx` qui lit
la première ligne et retourne `fields`, sans toucher au chemin
`.gpkg`/`.zip`/`.kml`/`.kmz` existant.

```bash
cd core && uv run pytest tests/test_ingestion_routes.py -v
```

- [ ] **Step 3 : régénérer OpenAPI/types TS**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Diff attendu **non vide** (`InspectResponse.fields` nouveau).

- [ ] **Step 4 : commit**

```bash
git add core/app/ingestion/schemas.py core/app/ingestion/routes.py core/tests/test_ingestion_routes.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
feat(core): POST /uploads/inspect retourne les en-têtes d'un XLSX

Ferme GAP-09 côté inspection (chantier 4.14) : InspectResponse.fields
(nouveau, optionnel) pour XLSX, layers inchangé pour GPKG/Shapefile/
KML/KMZ, aucun changement pour GeoParquet (pas de concept de couches).
EOF
)"
```

---

## Task 6 : frontend `ImportFileButton.tsx`

**Files:**
- Modify: `shell/src/shell/ImportFileButton.tsx`
- Test: `shell/src/shell/ImportFileButton.test.tsx`
- E2E: nouveau test dans `shell/e2e/` (vérifier s'il existe déjà un
  `import.spec.ts` ou équivalent avant d'en créer un — `find shell/e2e
  -iname "*import*"` n'en a trouvé aucun à l'écriture de la spec,
  confirmer à nouveau au moment de cette tâche).

**Interfaces:**
- Consumes: `client.inspectUpload` (étendu Tâche 5, réponse `fields`
  possible en plus de `layers`), `client.createIngestionJob` (inchangé).
- Produces: `accept` étendu, nouvelle logique de détection XLSX.

- [ ] **Step 1 : écrire les tests du composant (avant le code)**

Dans `ImportFileButton.test.tsx` (lire le fichier existant en entier
d'abord pour connaître le patron de mock du client déjà en place) :
- un test qui sélectionne un fichier `.xlsx`, mock `inspectUpload` pour
  retourner `{ fields: ["nom", "lat", "lon"] }`, vérifie que
  `detectLatLon` reconnaît `lat`/`lon` et **saute** l'étape de sélection
  manuelle (comportement symétrique au CSV auto-détecté) ;
- un test `.xlsx` où `fields` ne contient pas de lat/lon détectable :
  vérifie que le formulaire de sélection manuelle s'affiche (réutilisation
  de l'UI déjà construite pour le CSV) ;
- un test `.kml`/`.kmz` avec plusieurs couches : vérifie le passage par
  `selecting-layer` (même flux que `.gpkg`/`.zip` aujourd'hui) ;
- un test `.parquet` : vérifie qu'aucun appel à `inspectUpload` n'est fait,
  le job est créé directement (comme `.geojson`/`.csv` aujourd'hui).

```bash
cd shell && npm run test -- ImportFileButton
# attendu : ÉCHEC sur les nouveaux cas
```

- [ ] **Step 2 : implémenter**

`accept=".geojson,.json,.csv,.xlsx,.kml,.kmz,.gpkg,.zip,.parquet"` (spec
§4.3). Renommer ou dupliquer `isLayeredFormat()` en une fonction qui couvre
`.gpkg`/`.zip`/`.kml`/`.kmz`, et une condition séparée `needsFieldInspection()`
(ou nom équivalent) pour `.xlsx` qui appelle `inspectUpload` puis applique
`detectLatLon(response.fields ?? [])` exactement comme le fait déjà
`onFileChange` pour le CSV (réutiliser l'état `csvHeaders`/le rendu
existant du formulaire manuel, pas une deuxième UI).

```bash
cd shell && npm run test -- ImportFileButton
```

- [ ] **Step 3 : E2E**

Un scénario d'import `.xlsx` bout en bout (upload → détection/saisie
lat/lon → job → navigation vers `/maps/{itemId}`), même patron que les
scénarios d'import GPKG/Shapefile déjà couverts en E2E si un tel test
existe (vérifier — sinon, ce test E2E est le premier de sa sorte pour ce
bouton, à construire à partir du scénario `catalog.spec.ts` existant qui
ouvre déjà `ImportFileButton` indirectement, si applicable).

```bash
cd shell && npm run e2e
```

- [ ] **Step 4 : suite complète + commit**

```bash
cd shell && npm run lint && npm run test && npm run build
git add shell/src/shell/ImportFileButton.tsx shell/src/shell/ImportFileButton.test.tsx shell/e2e/
git commit -m "$(cat <<'EOF'
feat(shell): accepte XLSX/KML/KMZ/GeoParquet dans l'import de fichier

Ferme GAP-09 côté shell (chantier 4.14) : accept étendu à 9 extensions,
détection lat/lon XLSX via /uploads/inspect (réutilise detectLatLon et
le formulaire manuel déjà construits pour le CSV), KML/KMZ dans le
même flux de sélection de couche que GPKG/Shapefile.
EOF
)"
```

---

## Clôture de plan

- [ ] **Suite complète finale** :

```bash
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports \
  && uv run pytest \
  && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell && npm run lint && npm run format:check \
  && npm run test && npm run build \
  && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold \
  && npm run e2e
uvx pre-commit run --all-files
```

- [ ] **Vérification de non-régression explicite (piège CLAUDE.md n°4)** :
  relancer un import réel des 4 formats déjà supportés
  (GeoJSON/CSV/GPKG/Shapefile zippé), pas seulement les 3 nouveaux, pour
  confirmer qu'aucun n'a régressé après le passage à un dispatch à 7
  branches.
- [ ] **Mettre à jour `CLAUDE.md`** (`### Livré`) avec une ligne SP-56 :
  XLSX (via lat/lon détecté ou saisi, coercition datetime), KML/KMZ (même
  famille que GPKG/Shapefile, sans `/vsizip/` pour `.kmz`), GeoParquet
  (via `geopandas.read_parquet`, pas `pyogrio` — pas de driver Parquet
  dans ce build), aucune nouvelle dépendance.
