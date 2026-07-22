# SP-6b — Ingestion v1 : GeoPackage et Shapefile zippé (`pyogrio`)

## 1. Contexte et périmètre

Suite de SP-6a (infra jobs `procrastinate` + import GeoJSON/CSV, clos
2026-07-12, cf. `docs/superpowers/specs/2026-07-12-sp6a-ingestion-jobs-geojson-csv-design.md`).
SP-6b est un **ajout net**, pas un refactor : mêmes tables, même API
`/uploads/*`, même pipeline `run_import`, même worker. Il ajoute :

- **Deux nouveaux formats** : GeoPackage (`.gpkg`) et Shapefile zippé
  (`.zip` contenant `.shp`/`.shx`/`.dbf`/`.prj`/`.cpg`), via `pyogrio`
  (wheels manylinux, GDAL/GEOS/PROJ embarqués — **aucun paquet système** à
  ajouter au `Dockerfile`, vérifié : `uv pip install pyogrio pyproj`
  s'installe et s'importe sans `apt-get install gdal-bin`).
- **Sélection de couche** : un GeoPackage (ou un zip contenant plusieurs
  shapefiles) peut avoir plusieurs couches. Un nouvel endpoint
  `POST /uploads/inspect` liste les couches après l'upload S3 ; le shell
  affiche un sélecteur seulement si plus d'une couche existe (symétrique au
  sélecteur lat/lon manuel du CSV en SP-6a).
- **Reprojection de CRS** : GPKG/Shapefile ont fréquemment un CRS natif
  ≠ WGS84 (Lambert-93, UTM…). Tout CRS résolu par `pyproj` est reprojeté en
  EPSG:4326 ; un CRS manquant ou non reconnu échoue net (fail-fast, même
  doctrine que SP-6a — pas d'import silencieusement faux).
- **Validation du critère M4** de la feuille de route (« GPKG 50k entités →
  carte partagée en <5 min ») : un test dédié synthétise un GPKG de 50 000
  entités et chronomètre `run_import` bout en bout contre un vrai PostGIS.

Décisions prises en amont de ce document (réponses de Tanguy, 2026-07-12) :

| Question | Décision |
|---|---|
| GPKG multi-couches | Lister les couches, l'utilisateur choisit (pas d'auto-sélection de la 1ʳᵉ, pas d'import multi-collections) |
| CRS non-WGS84 | Reprojeter tout CRS résolu par `pyproj` ; fail-fast si non résolu (pas de liste blanche) |
| Critère M4 | SP-6b le valide (fixture 50k entités, seuil automatisé documenté §11) |

## 2. Architecture

Extension du flux SP-6a (upload présigné → `POST /uploads` → job
`procrastinate` → `run_import`) avec une étape d'inspection **entre**
l'upload et la création du job, seulement pour `.gpkg`/`.zip` :

```
Shell                          Cœur (FastAPI)                    Worker (procrastinate)
  │─ POST /uploads/presign ────▶│ (inchangé, SP-6a)
  │◀── {uploadUrl, key} ────────│
  │─ PUT <uploadUrl> (fichier) ▶│ MinIO (inchangé, SP-6a)
  │                              │
  │─ POST /uploads/inspect      │  seulement .gpkg/.zip : télécharge l'objet
  │   {key, filename} ──────────▶│  S3 dans un fichier temporaire, liste les
  │◀── {layers:[{name,          │  couches (pyogrio.list_layers +
  │     featureCount,           │  read_info par couche), pas de job créé
  │     geometryType}]} ─────────│
  │                              │
  │─ POST /uploads {..., │
  │   layerName?} ───────────────▶│ (inchangé sauf champ layerName, SP-6a)
  │                              │  ...
```

`layer_name` est ignoré par les formats GeoJSON/CSV (même précédent que
`lat_field`/`lon_field`, déjà ignorés par la branche GeoJSON en SP-6a).

## 3. Modèle de données

Migration `0010_ingestion_jobs_layer_name.py` : une colonne nullable sur
`ingestion_jobs`, même patron que `lat_field`/`lon_field` :

```python
op.add_column("ingestion_jobs", sa.Column("layer_name", sa.String(), nullable=True))
```

## 4. API

- **`POST /uploads/inspect`** `{key, filename}` → `200
  {layers: [{name, featureCount, geometryType}]}`.
  - Même garde 400 anti confused-deputy que `POST /uploads` (clé préfixée
    par le tenant de l'appelant).
  - 400 si le format déduit de `filename` n'est ni `.gpkg` ni `.zip`
    (« format non concerné par l'inspection »).
  - 422 si le fichier est illisible par GDAL (`DataSourceError`) — message
    renvoyé tel quel, pas de job créé, rien à auditer (lecture seule, aucun
    état persistant).
  - Ne crée **aucune** ligne `ingestion_jobs` : c'est une lecture, symétrique
    à l'aperçu d'en-têtes CSV (fait côté client en SP-6a) mais forcément
    côté serveur ici (GPKG est un format binaire SQLite, pas parsable dans
    le navigateur sans dépendance lourde).
- **`POST /uploads`** : `IngestionJobCreate` gagne `layerName: str | None`.
  Comportement inchangé sinon.

## 5. Parsing (`core/app/ingestion/parsers.py`, extension du fichier SP-6a)

Vérifié en amont avec `pyogrio==0.13.0` / `pyproj==3.7.2` (planchers du
`pyproject.toml` : `pyogrio>=0.9`, `pyproj>=3.6` — API bas-niveau utilisée
stable depuis les premières versions 0.x) :

```python
def list_layers(content: bytes, filename: str) -> list[LayerInfo]:
    """pyogrio.list_layers() + read_info() par couche — métadonnées seules,
    aucune lecture de géométrie."""

def parse_gpkg(content: bytes, layer_name: str | None) -> Iterator[tuple[BaseGeometry, dict]]:
    """pyogrio.raw.read() sur fichier temporaire, force_2d=True, reprojection
    CRS→WGS84 si nécessaire."""

def parse_shapefile_zip(content: bytes, layer_name: str | None) -> Iterator[tuple[BaseGeometry, dict]]:
    """Identique à parse_gpkg mais via /vsizip/<tmp>.zip (GDAL ouvre le zip
    directement, pas d'extraction manuelle)."""
```

Points techniques verrouillés par des vérifications manuelles (pas des
suppositions) :

- `pyogrio.raw.read()` retourne `(meta, index, geometry_wkb, field_data)` —
  `geometry_wkb` un `ndarray` de WKB bytes (`shapely.from_wkb(...)` pour
  reconstruire), `field_data` une liste de `ndarray` (un par champ, dtype
  `object`/`int64`/`float64`/`bool` selon la colonne).
- Les scalaires numpy (`np.int64`, `np.bool_`…) ne passent **pas**
  `isinstance(x, int)` (`np.int64` ne dérive pas de `int` — vérifié :
  `isinstance(np.int64(5), int) is False`). Chaque valeur de propriété doit
  être normalisée via `.item()` avant d'atteindre `_sql_type_for` (existant,
  SP-6a) sous peine de colonnes systématiquement typées `text`. Les `NaN`
  flottants (champs numériques absents) sont normalisés en `None`.
- CRS : `meta["crs"]` (chaîne `"EPSG:xxxx"` ou `None`). Reprojection via un
  seul `pyproj.Transformer.from_crs(src, "EPSG:4326", always_xy=True)`
  **construit une fois par parse** (jamais par feature — coût non
  négligeable à 50k entités) puis appliqué par géométrie. CRS déjà WGS84 :
  transform sauté (comparaison `pyproj.CRS`, `==` fonctionne, vérifié). CRS
  `None` ou non résolu : `pyproj.CRS.from_user_input(...)` lève
  `pyproj.exceptions.CRSError` (vérifié, y compris pour `None`) → capturé et
  relevé en `IngestionParseError`.
- Couche non trouvée (`layer_name` fourni mais absent du fichier), fichier
  illisible, zip sans aucune couche OGR reconnue (`pyogrio.errors.
  DataSourceError`/`DataLayerError`, tous deux sous-classes de
  `RuntimeError` mais capturés explicitement par nom, pas par
  `RuntimeError` générique) → `IngestionParseError` avec message listant
  les couches disponibles quand c'est pertinent.
- `force_2d=True` à la lecture : toute coordonnée Z est tronquée
  silencieusement (documenté §10, hors périmètre — la table PostGIS créée
  par `run_import` est 2D comme en SP-6a).
- Géométries invalides (`geom.is_valid is False`) ou nulles (WKB manquant) :
  même garde fail-fast que GeoJSON/CSV.

Aucune dépendance `numpy` à ajouter explicitement à `pyproject.toml` — déjà
tirée transitivement par `shapely`/`pyogrio` (présente depuis SP-6a).

## 6. Import PostGIS (`core/app/ingestion/importer.py`)

- `_pick_format()` reconnaît `.gpkg` → `"gpkg"`, `.zip` → `"shapefile"`.
- `run_import()` gagne un paramètre `layer_name: str | None = None`,
  transmis aux deux nouveaux parseurs ; ignoré par les branches
  `geojson`/`csv` (même précédent que `lat_field`/`lon_field` déjà ignorés
  par la branche `geojson`).
- Aucun autre changement : le reste du pipeline (colonnes inférées, table
  PostGIS, `register_collection`, item carte, audit) est déjà générique sur
  `list[tuple[BaseGeometry, dict]]`, indépendant du format source.
- **Pas de changement à l'insertion par lots** : benchmark manuel (psycopg3
  `executemany`, 50 000 lignes point+2 colonnes contre un PostGIS réel,
  conteneur jetable) — 0,8 s en un seul appel, 0,67-0,68 s en lots de
  2000/5000. L'insertion actuelle (un seul appel `session.execute(text(...),
  params)`) n'est pas le goulot pour le volume visé par M4 ; ajouter un
  découpage en lots serait de la complexité sans bénéfice mesuré (YAGNI).

## 7. UI shell (`shell/src/shell/ImportFileButton.tsx`)

1. `accept` du `<input type="file">` gagne `.gpkg,.zip`.
2. Après l'upload S3 (`uploadToPresignedUrl`), si le fichier est
   `.gpkg`/`.zip` : appel `client.inspectUpload({key, filename})`.
   - 1 couche → `layerName` retenu automatiquement, pas d'étape visible.
   - >1 couche → `<select aria-label="Couche à importer">` listant
     `name (featureCount entités)`, doit être choisi avant de continuer
     (même contrainte que le sélecteur lat/lon CSV de SP-6a).
   - 0 couche ou erreur d'inspection → passe en phase `error` avec le
     message renvoyé par le cœur.
3. `createIngestionJob` transmet `layerName` (nouveau champ optionnel du
   payload existant).
4. Poll/redirection : inchangés (SP-6a).

`ItemClient` (`shell/src/api/itemClient.ts` + `types.ts`) : nouvelle méthode
`inspectUpload(input: {key, filename}): Promise<{layers: LayerInfo[]}>` ;
`createIngestionJob` gagne `layerName?: string` dans son type d'entrée.
`core-schema.d.ts` régénéré (`npm run gen:api-types`) après l'ajout du
endpoint côté cœur.

## 8. Permissions

Inchangées : tout utilisateur authentifié peut uploader/inspecter (même
règle que SP-6a) ; `POST /uploads/inspect` ne touche aucune donnée
persistante, pas de vérification de propriété au-delà du préfixe tenant de
la clé S3.

## 9. Tests

- **Cœur**, formats/CRS/couches — **fixtures synthétisées en mémoire dans
  les tests eux-mêmes** via `pyogrio.raw.write()` (pas de binaire committé) :
  - `list_layers()` : 1 couche, 2 couches (GPKG), zip shapefile (1 couche
    nommée d'après le fichier `.shp`), fichier corrompu, zip sans couche
    OGR reconnue.
  - `parse_gpkg`/`parse_shapefile_zip` : géométrie + propriétés (dont un
    champ entier — vérifie la normalisation numpy), CRS EPSG:4326 (aucune
    transformation), CRS EPSG:2154 (reprojection, coordonnées vérifiées à
    la tolérance), CRS absent/inconnu (fail-fast), `layer_name` absent du
    fichier (fail-fast), géométrie nulle (fail-fast).
  - Intégration (`postgis`) : import GPKG/shapefile bout en bout
    (`run_import`) — collection interrogeable, item carte, coordonnées
    reprojetées correctes en base.
  - **Perf/M4** (`postgis`) : GPKG 50 000 points synthétisé en mémoire →
    `run_import` chronométré, assertion generous (§11) + comptage de lignes.
  - API : `POST /uploads/inspect` (couches retournées, 400 clé étrangère,
    400 format non concerné, 422 fichier illisible) ; `POST /uploads` avec
    `layerName`.
- **Shell** : `ImportFileButton` — sélecteur de couche affiché seulement si
  >1 couche, `layerName` transmis, chemin auto-sélection à 1 couche.
- **E2E** (19ᵉ spec, `shell/e2e/ingestion-gpkg.spec.ts`) : upload d'un GPKG à
  2 couches → sélection d'une couche → item carte visible avec les entités.

## 10. Hors périmètre (rappel)

- Détection de CRS pour GeoJSON/CSV (déjà WGS84 supposée, SP-6a, inchangé).
- Coordonnées Z/3D (tronquées silencieusement, `force_2d=True`).
- KML, MapInfo TAB, ou tout autre format lisible par `pyogrio` mais non cité
  par la feuille de route — pas ajoutés sans besoin utilisateur exprimé.
- Suivi de job en direct, PMTiles/tippecanoe pour les très grosses couches
  (>50k, streaming GDAL) → SP-6c, inchangé depuis SP-6a.
- Ajout à une collection existante (upsert) → toujours hors périmètre,
  inchangé depuis SP-6a.
- Rendu le zip invalide explicite s'il contient plusieurs `.shp` sans lien
  logique entre eux : traité comme un GPKG multi-couches ordinaire (liste +
  sélection), pas de garde spécifique supplémentaire.

## 11. Critères d'acceptation (SP-6b)

- Un GeoPackage à une seule couche s'importe sans étape de sélection
  visible ; un GeoPackage à plusieurs couches force la sélection avant de
  continuer.
- Un Shapefile zippé (`.shp`/`.shx`/`.dbf`/`.prj`) s'importe comme un GPKG à
  une couche.
- Un fichier en CRS projeté (ex. Lambert-93) produit une collection dont les
  coordonnées sont en WGS84, vérifiées à la tolérance en base.
- Un CRS manquant ou non reconnu produit `status="error"` avec un message
  lisible, jamais un import silencieusement mal projeté.
- **M4** : un GPKG synthétique de 50 000 entités points s'importe via
  `run_import` en un temps mesuré et documenté dans le rapport de tâche,
  sous un seuil automatisé (voir plan, Task 5) largement inférieur au
  budget de 5 minutes de la feuille de route (le budget couvre aussi le
  transfert réseau du fichier, hors périmètre d'un test backend).
- Toutes les specs E2E existantes (18) restent vertes + la nouvelle (19).
