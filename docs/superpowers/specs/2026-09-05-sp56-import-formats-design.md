# SP-56 — Import : formats manquants (XLSX, KML/KMZ, GeoParquet)

Date : 2026-09-05. Ferme le chantier **4.14** de la vague 4
(`docs/vision/2026-08-20-revue-projet-et-plan-daction.md:409`), recensé par
la revue SP-42 sous **GAP-09** (et sa paire de mesure d'écart au marché,
**GAP-29** — même coût, pas de travail supplémentaire) :
`docs/revue/2026-09-04-analyse-gaps.md:53,120`.

**Aucune dépendance sur SP-43.**

## Contexte et périmètre

**Vérifié avant d'écrire ce document, contre le pipeline d'ingestion réel**
(`core/app/ingestion/`, SP-6, jamais retouché depuis sauf SP-42 Tâche 6 —
commentaire de renommage sans changement fonctionnel) :

- `core/app/ingestion/parsers.py` a 4 parseurs : `parse_geojson`,
  `parse_csv_latlon`, `parse_gpkg`, `parse_shapefile_zip` — les 3 derniers
  s'appuient sur `pyogrio` (GDAL embarqué, wheel manylinux, aucun paquet
  système requis — confirmé par le commentaire d'en-tête du fichier).
- `core/app/ingestion/importer.py::_pick_format` (lignes 51-61) dispatch
  sur l'extension du fichier et lève `IngestionParseError` pour tout ce qui
  n'est pas `.geojson`/`.json`/`.csv`/`.gpkg`/`.zip`.
- `core/app/ingestion/parsers.py::list_layers` (lignes 199-227) n'inspecte
  que `.gpkg`/`.zip` (utilisé par `POST /uploads/inspect` pour proposer un
  choix de couche à l'utilisateur avant de créer le job d'import).
- Côté shell, `shell/src/shell/ImportFileButton.tsx` a un seul point de
  contrôle des formats acceptés : l'attribut `accept=".geojson,.json,.csv,.gpkg,.zip"`
  (ligne 214) et la fonction `isLayeredFormat()` (lignes 23-26, teste
  `.gpkg`/`.zip`) qui décide si un appel à `POST /uploads/inspect` est fait
  avant de créer le job.
- **Vérifié par exécution réelle dans l'environnement du dépôt** (`cd core
  && uv run python`, mêmes versions que `core/pyproject.toml`) — pas
  supposé (piège CLAUDE.md n°3) :
  - `pyogrio.list_drivers()` rapporte le driver `KML` en `"rw"` et
    `LIBKML` en `"raw"` : lisible par `pyogrio.raw.read` sans paquet
    système supplémentaire (contrairement à `libexpat1`, déjà un piège
    payé une fois sur ce dépôt pour `defusedxml`, cf. CLAUDE.md — vérifié
    que ce n'est **pas** le même risque ici, `pyogrio` embarque son propre
    GDAL/libkml).
  - Un fichier `.kmz` (zip contenant un `doc.kml`) est lu **directement**
    par `pyogrio.list_layers()`/`pyogrio.raw.read()`, **sans** le
    préfixe `/vsizip/` qu'exige `.zip` (Shapefile) — GDAL détecte le driver
    `LIBKML` sur l'extension `.kmz` lui-même. Piège potentiel si on
    calquait aveuglément le traitement `.zip` existant (`parse_shapefile_zip`
    préfixe `/vsizip/`, ce qui casserait la lecture d'un `.kmz`).
  - `pyogrio.list_drivers()["Parquet"]` vaut `None` (**pas** de driver OGR
    Parquet dans ce build de `pyogrio`) — GeoParquet ne peut **pas**
    passer par `_read_features`/`pyogrio.raw.read` comme GPKG/Shapefile.
    En revanche `geopandas.read_parquet()` (déjà une dépendance du dépôt,
    utilisée en écriture par `core/app/cdc/parquet_writer.py::write_geoparquet`,
    SP-11) lit correctement un GeoParquet 1.0 produit par cette même
    fonction — vérifié par un aller-retour écriture/lecture réel dans cet
    environnement.
  - `openpyxl` (déjà une dépendance, `core/pyproject.toml:61`, utilisée en
    écriture par `core/app/analytics/export.py::rows_to_xlsx`, SP-16a) lit
    un classeur via `load_workbook(BytesIO(content), read_only=True,
    data_only=True)` — aucune dépendance nouvelle à ajouter pour aucun des
    3 formats de ce SP.

**Conséquence de conception** : aucune nouvelle dépendance Python, aucun
changement de `Dockerfile` — seulement des extensions de code dans
`app/ingestion/`. C'est délibérément le patron d'extension existant qui est
suivi (piège CLAUDE.md n°9 du brief : ne pas dupliquer le pipeline
d'ingestion, l'étendre).

## 1. XLSX — traité comme un CSV avec en-têtes lat/lon

### 1.1 Nuance sur le critère de sortie

Le texte du chantier dit : « Importer le XLSX qu'on vient d'exporter
fonctionne, sans conversion manuelle. » **Vérifié contre l'export réel**
(`core/app/analytics/export.py::features_to_format`, lignes 120-130) :
l'export XLSX d'entités (`format in ("csv", "xlsx")`) sérialise
**uniquement `properties`** — la géométrie est explicitement abandonnée
(commentaire d'en-tête du fichier : « mode agrégé, sans géométrie par
construction »). Un aller-retour export→import XLSX ne peut donc
fonctionner **que** si les `properties` de la collection source
contenaient déjà des colonnes latitude/longitude exploitables (cas réel et
fréquent — un jeu de points d'intérêt géocodés qui conserve lat/lon comme
attributs, au-delà de la géométrie PostGIS) — pas pour un export d'une
collection dont la géométrie n'est jamais dupliquée en attribut. C'est la
**même limite** que l'import CSV actuel (déjà accepté, jamais traité comme
un défaut) — pas une régression introduite par ce SP, un fait à documenter
explicitement pour ne pas laisser croire que *tout* export XLSX est
réimportable tel quel.

### 1.2 Parseur

Nouvelle fonction `core/app/ingestion/parsers.py::parse_xlsx_latlon`,
signature miroir de `parse_csv_latlon(content, lat_field, lon_field)` :

1. `openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)`,
   première feuille active (`wb.active`) — pas de sélection de feuille en
   v1 (voir §1.4 hors périmètre).
2. Première ligne = en-têtes (`ws.iter_rows(max_row=1, values_only=True)`),
   même détection auto `detect_lat_lon_fields` déjà utilisée par le CSV
   (réutilisée telle quelle, pas dupliquée).
3. Lignes suivantes → `(Point(lon, lat), properties)`, même contrat que les
   autres parseurs (`IngestionParseError` fail-fast sur une ligne
   invalide, même message de forme que `parse_csv_latlon`).
4. **Coercition de valeur nécessaire, absente du CSV** : `openpyxl` rend
   des types Python natifs par cellule (`int`, `float`, `str`, `bool`,
   `datetime.datetime`, `None`) — contrairement au CSV, où tout est déjà
   `str`. Une cellule date tomberait dans le repli `"text"` de
   `importer.py::_sql_type_for` (qui ne reconnaît que `bool`/`int`/`float`)
   alors que la valeur réelle est un objet `datetime`, pas une chaîne —
   l'insertion SQL échouerait ou produirait une valeur illisible selon le
   driver. Sérialiser toute valeur `datetime`/`date` en `isoformat()`
   **dans le parseur lui-même**, avant que la ligne n'atteigne
   `importer.py` — même principe que `_native_value()` dans
   `_read_features` (ligne ~155), qui fait déjà cette normalisation pour
   les scalaires `numpy`/NaN issus de `pyogrio`.

### 1.3 Dispatch

`importer.py::_pick_format` : `.xlsx` → `"xlsx"`. `run_import()` : nouvelle
branche `elif fmt == "xlsx": rows = list(parse_xlsx_latlon(content,
lat_field, lon_field))` — réutilise `lat_field`/`lon_field` déjà présents
sur `IngestionJobCreate` (aucun champ de schéma nouveau nécessaire, ces deux
champs sont déjà génériques).

### 1.4 Hors périmètre

- Sélection de feuille (un classeur à plusieurs feuilles utilise
  silencieusement `wb.active`) — pas de concept de « couches » pour XLSX
  dans ce SP, contrairement à GPKG/Shapefile/KML. Si une vraie demande
  apparaît, traiter par un paramètre `sheetName` optionnel, même patron que
  `layerName` — hors budget de ce SP (3-6j pour les 3 formats).
- Cellules formule (`data_only=True` lit la **dernière valeur calculée
  mise en cache par Excel**, pas la formule elle-même ni un recalcul — un
  classeur jamais ouvert dans Excel après une modification de formule
  peut avoir une valeur en cache périmée. Comportement d'`openpyxl`, pas
  un choix de ce SP, mais à documenter dans le message d'erreur ou l'aide
  utilisateur si ça revient comme confusion réelle plus tard).

## 2. KML/KMZ — même famille que GPKG/Shapefile, sans le préfixe `/vsizip/`

### 2.1 Parseur et inspection de couches

`_read_features` (déjà générique sur un chemin de fichier temporaire) est
directement réutilisable — aucune nouvelle fonction de parsing de bas
niveau nécessaire, seulement deux nouveaux points d'entrée qui l'appellent
avec le bon suffixe :

```python
def parse_kml(content: bytes, layer_name: str | None = None) -> Iterator[tuple[BaseGeometry, dict]]:
    suffix = ...  # ".kml" ou ".kmz" selon l'appelant — voir §2.2 (dispatch par extension réelle)
    with _temp_file(content, suffix) as path:
        yield from _read_features(path, layer_name)  # PAS de /vsizip/, contrairement à parse_shapefile_zip
```

`list_layers()` (lignes 199-227) : ajouter une branche `.kml`/`.kmz` avec
`wrap = lambda p: p` (identité — **ne pas** réutiliser le `wrap` de la
branche `.zip`, qui préfixe `/vsizip/` et casserait la lecture d'un `.kmz`,
cf. §Contexte).

### 2.2 Dispatch

`_pick_format` : `.kml`/`.kmz` → `"kml"`. `run_import()` : nouvelle branche
`elif fmt == "kml": rows = list(parse_kml(content, layer_name))` —
`layer_name` déjà présent sur le schéma, même mécanique de sélection de
couche que GPKG/Shapefile (un KML avec plusieurs `Folder`/couches internes
peut nécessiter un choix explicite, exactement le même flux
`/uploads/inspect` → `selecting-layer` déjà câblé côté shell pour
GPKG/Shapefile).

### 2.3 Hors périmètre

- Styles KML (`<Style>`, icônes, couleurs) : ignorés, seules géométrie +
  attributs (`<ExtendedData>`/`<SimpleData>`, ce que GDAL expose comme
  champs de couche) sont importés — cohérent avec le traitement déjà
  appliqué à GPKG/Shapefile (aucun style de source n'est jamais importé).
- Networklinks KML (référence à un autre fichier distant) : non suivis,
  comportement par défaut de GDAL (probablement ignoré silencieusement ou
  en erreur selon la config — à vérifier par un test dédié si un cas réel
  se présente, pas anticipé ici).

## 3. GeoParquet — parseur dédié, PAS `pyogrio`

### 3.1 Parseur

Nouvelle fonction, dans un module séparé pour ne pas mélanger les deux
familles de dépendances géospatiales du fichier (`pyogrio` vs
`geopandas`/`pyarrow`) — au choix de l'exécutant : soit directement dans
`parsers.py` (déjà nommé génériquement, pas un problème de frontière de
module), soit `core/app/ingestion/geoparquet.py` si la taille du fichier le
justifie à l'exécution :

```python
def parse_geoparquet(content: bytes) -> Iterator[tuple[BaseGeometry, dict]]:
    with _temp_file(content, ".parquet") as path:
        gdf = geopandas.read_parquet(path)
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)  # geopandas gère lui-même la reprojection colonne géométrie
        geom_col = gdf.geometry.name
        for _, row in gdf.iterrows():
            geom = row[geom_col]
            if geom is None:
                raise IngestionParseError("entité sans géométrie")
            props = {k: _native_value(v) for k, v in row.items() if k != geom_col}
            yield geom, props
```

Pas de couche multiple (un fichier `.parquet` = une seule table, pas de
concept de couches internes chez GDAL/GeoParquet à ce jour — vérifié :
`pyogrio.list_drivers()["Parquet"]` est `None`, donc `list_layers()` ne
doit **pas** recevoir de branche `.parquet` : ce format ne passe jamais par
l'étape d'inspection/sélection de couche, comme GeoJSON/CSV aujourd'hui).
`_native_value` (déjà défini dans `parsers.py` pour les scalaires
`numpy`/NaN de `pyogrio`) est directement réutilisable ici aussi — les
colonnes non-géométrie d'un GeoDataFrame sont typées `numpy`/`pandas`, même
classe de valeurs à normaliser.

### 3.2 Dispatch

`_pick_format` : `.parquet` → `"geoparquet"`. `run_import()` : nouvelle
branche `elif fmt == "geoparquet": rows = list(parse_geoparquet(content))`.

### 3.3 Hors périmètre

- Lecture d'un GeoParquet **partitionné** (répertoire de fragments,
  convention Hive) : seul un fichier unique est supporté, cohérent avec la
  sortie du CDC (`core/app/cdc/parquet_writer.py` écrit un seul fichier par
  lot).
- CRS non standard sans table EPSG résolvable par `pyproj` : même
  comportement d'échec que `_crs_transform()` pour GPKG/Shapefile (lève
  `IngestionParseError`), pas de traitement spécial.

## 4. Points communs aux trois formats

### 4.1 `IngestionJobCreate`/`InspectRequest` (schémas) — aucun changement de forme

`core/app/ingestion/schemas.py` n'a besoin d'aucun nouveau champ : `latField`/
`lonField` (déjà génériques, réutilisés par XLSX comme par CSV) et
`layerName` (déjà générique, réutilisé par KML/KMZ comme par GPKG/Shapefile)
couvrent les 3 nouveaux formats sans extension de schéma. Seul
`InspectResponse` a potentiellement besoin d'un ajustement pour le cas XLSX
— voir §4.2.

### 4.2 Détection lat/lon pour XLSX côté shell — pas de lecture binaire côté client

`ImportFileButton.tsx::onFileChange` détecte aujourd'hui les en-têtes CSV
en lisant les 4096 premiers octets du fichier **côté navigateur**
(`FileReader.readAsText`, ligne 74-84) — ça ne fonctionne pas pour un
`.xlsx` (format binaire zippé, pas du texte). Deux options :

- **(retenue)** Réutiliser `/uploads/inspect` (déjà appelé pour
  GPKG/Shapefile — `isLayeredFormat()`) pour les fichiers XLSX aussi, mais
  avec une réponse différente : étendre `InspectResponse`
  (`core/app/ingestion/schemas.py`) d'un champ optionnel `fields:
  list[str] | None = None`, peuplé pour `.xlsx` (lecture de la première
  ligne uniquement, `openpyxl.load_workbook(..., read_only=True)` puis
  `next(ws.iter_rows(max_row=1, values_only=True))` — pas besoin de charger
  tout le classeur juste pour l'inspection). Le shell appelle
  `inspectUpload` pour XLSX (nouvelle condition, distincte de
  `isLayeredFormat()` — proposer de la renommer `needsInspect()` ou
  d'ajouter une fonction `needsFieldInspection()` séparée, au choix de
  l'exécutant, la duplication de nom n'est pas grave ici), applique
  `detectLatLon(fields)` (déjà existant, générique sur une liste de
  chaînes) exactement comme pour le CSV, et si non détecté, réutilise le
  même état `csvHeaders`/formulaire manuel de sélection lat/lon déjà
  construit pour le CSV — pas de nouvelle UI de saisie manuelle à écrire,
  seulement une nouvelle **source** de la liste de champs.
- (rejetée) Parser le XLSX côté navigateur avec une bibliothèque JS dédiée
  (ex. SheetJS) : nouvelle dépendance front, format de fichier binaire
  complexe à parser correctement en JS pour un seul besoin (lire une ligne
  d'en-tête) — le serveur sait déjà le faire avec une dépendance déjà
  présente (`openpyxl`), pas de raison de dupliquer côté client.

### 4.3 Frontend — un seul point de contrôle des extensions acceptées

`ImportFileButton.tsx` :
- `accept=".geojson,.json,.csv,.xlsx,.kml,.kmz,.gpkg,.zip,.parquet"` (ligne
  214, seule occurrence de cette liste dans le dépôt — vérifié par
  `grep -rn` avant d'écrire ce document).
- `isLayeredFormat()` (lignes 23-26) : ajouter `.kml`/`.kmz` (couches
  multiples possibles, même flux `selecting-layer` que GPKG/Shapefile).
  **Ne pas** y ajouter `.xlsx` (flux différent, §4.2) ni `.parquet` (aucune
  inspection, va directement à `startJob`, comme GeoJSON/CSV aujourd'hui).

### 4.4 Pas de nouvelle garde d'autorisation

`POST /uploads` est déjà gardé par `data.manage` + `maps.manage`
(`core/app/ingestion/routes.py:112-122`, corrigé par SP-42) — ce garde
s'applique uniformément quel que soit le format du fichier, aucun
changement nécessaire ici.

## 5. Hors périmètre explicite (transverse aux 3 formats)

- Limite de taille de fichier / nombre de lignes : aucune limite
  n'existe aujourd'hui dans le pipeline (`rows = list(...)` charge tout en
  mémoire, quel que soit le format) — ce SP n'en introduit pas non plus,
  ni ne corrige ce manque préexistant (hors sujet du chantier 4.14).
- Détection de format par contenu (« sniffing » du contenu réel plutôt que
  de l'extension du nom de fichier) : `_pick_format` reste basé sur
  l'extension, comme aujourd'hui pour les 4 formats existants — un
  `.xlsx` renommé `.zip` échouerait au parsing avec le message d'erreur du
  format supposé, pas une détection plus intelligente.
- Export : ce SP ne touche que l'**import**. XLSX est déjà exporté
  (SP-16a) ; KML/KMZ et GeoParquet ne sont exportables nulle part
  aujourd'hui et ce SP ne change pas ça (chantier distinct si demandé).

## 6. Critères de sortie

- Importer un `.xlsx` avec des colonnes lat/lon détectables
  automatiquement (ou sélectionnées manuellement) crée une collection et
  un item carte, comme un CSV équivalent.
- Importer un `.kml` (une seule couche) ou un `.kmz` (zip contenant un
  `.kml`) crée une collection et un item carte ; un KML à plusieurs couches
  déclenche le même flux de sélection de couche que GPKG/Shapefile.
- Importer un `.parquet` GeoParquet 1.0 (par exemple celui produit par le
  CDC, `core/app/cdc/parquet_writer.py`) crée une collection et un item
  carte, sans passer par un flux de sélection de couche.
- Les 4 formats déjà supportés (GeoJSON, CSV, GPKG, Shapefile zippé)
  continuent de fonctionner à l'identique — aucune régression sur le
  dispatch existant.

## 7. Décomposition en tâches (indicatif, affiné en plan)

1. Parseur XLSX (`parse_xlsx_latlon` + coercition datetime) + tests.
2. Parseur KML/KMZ (extension de `_read_features`/`list_layers`) + tests.
3. Parseur GeoParquet (`parse_geoparquet`) + tests.
4. Intégration `importer.py` (`_pick_format` + `run_import`, les 3 formats)
   + tests d'intégration bout en bout (fichier réel → collection → item).
5. `POST /uploads/inspect` étendu (`InspectResponse.fields` pour XLSX,
   `list_layers` pour KML/KMZ) + tests.
6. Frontend `ImportFileButton.tsx` (accept, `isLayeredFormat`, inspection
   XLSX) + tests unitaires + E2E.
