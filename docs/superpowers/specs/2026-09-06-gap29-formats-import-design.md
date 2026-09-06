# GAP-29 — Formats d'import supplémentaires (Excel multi-feuilles, Parquet
non-géo, JSON Lines, CSV/WKT, GML/INSPIRE, XML générique)

Date : 2026-09-06. Ferme **GAP-29** (`docs/revue/2026-09-04-analyse-gaps.md`) :
l'écart de largeur de couverture des formats d'import face au marché (FME et
équivalents proposent 450+ connecteurs ; GeoStudio en avait 4 avant SP-56 —
GeoJSON/CSV/GPKG/Shapefile — puis 7 après SP-56 — +XLSX/KML+KMZ/GeoParquet).
Ce chantier a été cadré par brainstorming direct avec Tanguy (pas de nouvelle
session de brainstorm nécessaire) : le périmètre, les 6 formats retenus et
l'architecture de la fonction pivot d'extraction de géométrie sont des
décisions déjà prises, reproduites et justifiées ci-dessous. Portée assumée
dès le départ : **anticipation générique** (aucun cas d'usage client précis
aujourd'hui) → investissement minimal, aucune UX riche, réutilisation
maximale du patron déjà posé par SP-56.

## 0. Formats retenus (rappel)

1. **Excel multi-feuilles** — le parseur XLSX actuel ne lit que la feuille
   active (`wb.active`). Chaque feuille devient une entrée `LayerInfoOut`,
   réutilisant la phase `selecting-layer` déjà utilisée pour GPKG/KML
   multi-couches.
2. **Parquet non-géo** — partage l'extension `.parquet` avec le GeoParquet
   déjà supporté (SP-56). Détection par sniff de la clé `"geo"` dans les
   métadonnées du fichier (spec GeoParquet 1.0) : présente → `parse_geoparquet`
   existant ; absente → nouveau chemin tabulaire.
3. **JSON Lines** (`.jsonl`) — un objet JSON par ligne devient une table.
4. **CSV/WKT** — étend `parse_csv_latlon` : la géométrie peut venir d'une
   colonne WKT unique au lieu de deux colonnes lat/lon.
5. **GML/INSPIRE** — traité EXACTEMENT comme KML : réutilisation brute de
   `_read_features` (driver GDAL natif), aucune logique spécifique au schéma
   INSPIRE. Peut exposer plusieurs couches → réutilise aussi `selecting-layer`.
6. **XML générique** — pas de mapping XPath. Auto-détection heuristique de
   l'« élément répété » (le nom d'élément qui apparaît ≥2 fois au même niveau
   sous un même parent), aplatissement de ses enfants texte directs en
   colonnes.

## 1. Vérifié avant d'écrire (code réel, pas le récit)

### 1.1 Le pipeline d'ingestion aujourd'hui

`core/app/ingestion/parsers.py` (433 lignes) expose un parseur par format,
tous de la forme `Iterator[tuple[BaseGeometry, dict]]` : `parse_geojson`,
`parse_csv_latlon(content, lat_field, lon_field)`, `parse_xlsx_latlon(content,
lat_field, lon_field)`, `parse_gpkg`/`parse_shapefile_zip`/`parse_kml(content,
layer_name)` (tous les trois via `_read_features`, GDAL/pyogrio),
`parse_geoparquet(content)` (via `geopandas.read_parquet`, **pas** pyogrio —
aucun driver Parquet dans ce build). `list_layers(content, filename)` énumère
les couches d'un GPKG/Shapefile/KML/KMZ pour l'étape `selecting-layer` côté
shell ; `read_xlsx_header_fields(content)` lit uniquement l'en-tête de la
feuille active pour l'étape `selecting-latlon`.

`core/app/ingestion/importer.py::run_import` : `_pick_format(filename)`
dispatch purement sur l'extension → `rows = list(parse_xxx(...))` → construit
dynamiquement les colonnes (union des clés de `props` rencontrées sur
**toutes** les lignes, type déduit de la première valeur non nulle,
`_sql_type_for` ne connaît que bool/int/float/texte) → `CREATE TABLE
public.ingest_<uuid> (id serial PRIMARY KEY, tenant_id text NOT NULL, <col
defs>, geom geometry(<type>, 4326))` → `INSERT` paramétré → `introspect_table`
→ `apply_collection_ddl` (RLS + GRANTs + index spatial) → `create_collection`
→ **toujours** un `Item(resource_type="map")` + `BuilderConfig(kind="map",
map=MapConfig(layers=[MapLayer(kind="feature", url=".../collections/{id}/items")]))`.

Le commentaire ligne 124-127 d'`importer.py` documente déjà, de lui-même, un
gap connu et non corrigé : *« Propriétés nommées "id" ou "geom" entreraient
en collision avec les colonnes fixes ci-dessous — cas non géré en v1 (hors
périmètre SP-6a) »*. SP-56 a corrigé ce cas précis pour KML uniquement,
parce que le driver GDAL KML impose un champ `id` sur **tout** Placemark
(collision garantie à 100 %, pas un cas limite) :
`_KML_RESERVED_PROPERTY_NAMES = {"id", "tenant_id", "geom"}` +
`_rename_kml_reserved_properties()` renomme en `kml_id`/`kml_tenant_id`/
`kml_geom`. Le gap général (n'importe quel CSV/XLSX/GeoJSON dont une colonne
s'appelle littéralement `id`) reste ouvert et **n'est pas fermé par ce SP**
(cf. §6 Hors périmètre) — sauf pour les deux nouveaux formats dont le fixture
réel choisi (§5) déclenche la collision de façon vérifiée, pas supposée.

### 1.2 `POST /uploads/inspect` et le contrat `InspectResponse`

`core/app/ingestion/schemas.py` :

```python
class InspectRequest(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)

class LayerInfoOut(BaseModel):
    name: str
    featureCount: int
    geometryType: str

class InspectResponse(BaseModel):
    layers: list[LayerInfoOut] = Field(default_factory=list)
    fields: list[str] | None = None

class IngestionJobCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    collectionTitle: str = Field(min_length=1)
    latField: str | None = None
    lonField: str | None = None
    layerName: str | None = None
```

`core/app/ingestion/routes.py::inspect_upload` : branche déjà spécifiquement
sur `.xlsx` (→ `read_xlsx_header_fields`, retourne `fields`), sinon appelle
`list_layers` (→ retourne `layers`). Aucune de ces deux branches ne reçoit
aujourd'hui de nom de couche/feuille en entrée — l'inspection est toujours
« tout le fichier », jamais « une feuille précise ».

### 1.3 `shell/src/shell/ImportFileButton.tsx`

Machine à états `Phase = "form" | "uploading" | "selecting-layer" |
"selecting-latlon" | "polling" | "error"`. `isLayeredFormat(filename)` (gpkg/
zip/kml/kmz) déclenche l'inspection puis, si `layers.length > 1`,
`selecting-layer` (sélecteur `<select>` de couche, `LayerInfo` = `{name,
featureCount, geometryType}`). `needsFieldInspection(filename)` (XLSX
seulement aujourd'hui) déclenche l'inspection puis, si `!detectLatLon(fields)`,
`selecting-latlon` (deux `<select>` lat/lon). Le CSV a un chemin **encore
différent** : sniff des en-têtes côté navigateur (`FileReader`, 4096 premiers
octets) **avant upload**, sans passer par `/uploads/inspect` du tout.
`startJob()` envoie toujours `latField`/`lonField`/`layerName` (jamais les
trois en même temps dans la pratique actuelle). `accept=".geojson,.json,.csv,
.xlsx,.kml,.kmz,.gpkg,.zip,.parquet"`.

### 1.4 Les couches applicatives tolèrent déjà l'absence de géométrie

Vérifié directement (pas supposé) — c'est le fait le plus important de cette
section, il change toute la conception de la option « aucune géométrie » :

- `Collection.geometry_column`/`geometry_type`/`srid` sont **déjà**
  `nullable=True` (`core/app/collections/models.py`).
- `introspect_table()` (`core/app/collections/introspection_pg.py`) gère déjà
  le cas `geom_rows` vide → les trois valeurs restent `None`, aucune erreur.
- `table_extent()` (`core/app/collections/extent.py`) retourne `None` si
  `info.geometry_column is None`, sans erreur.
- `apply_collection_ddl()` (`core/app/collections/ddl.py`) ne pose l'index
  spatial GiST que `if geom_col:` — no-op silencieux sinon, RLS/GRANTs/
  publication CDC s'appliquent quand même.
- `core/app/features/repository.py` (`_where`, `_select_list`,
  `_row_to_feature`, `insert_feature`, `replace_feature`) testent tous
  `if info.geometry_column` avant toute opération géométrique — OGC API
  Features lit/écrit déjà des collections sans géométrie.
- **Le flux admin `POST /collections` (`register_collection`,
  `core/app/collections/routes.py`) enregistre déjà aujourd'hui une table
  Postgres arbitraire sans colonne géométrie** — sans créer ni Item, ni
  Config, ni carte. C'est le précédent direct et déjà en production pour
  « une collection peut ne pas avoir de géométrie ».

Conséquence : l'option « aucune géométrie » de ce chantier n'est **pas** une
extension du modèle de données — c'est un chemin déjà supporté par la couche
`collections`/`features`, simplement jamais atteint depuis l'ingestion par
fichier. Ce qui n'est **pas** déjà supporté et reste **hors périmètre** de ce
SP : le widget carte (`MapLayer(kind: "feature")`) suppose une géométrie pour
s'afficher — ce chantier ne crée donc **pas** de Map/Item/Config quand le mode
choisi est « aucune géométrie » (cf. §2.7, §6).

### 1.5 Dépendances déjà présentes (aucune nouvelle à ajouter)

`core/pyproject.toml`/`uv.lock` : `pyarrow>=15.0` (déjà tiré par
`geopandas`, utilisable directement pour sniffer les métadonnées Parquet
sans dépendance nouvelle), `defusedxml>=0.7` (déjà utilisé par
`app/mapicons/svg.py`/`app/harvest/connectors/ows.py` — **à réutiliser** pour
le parseur XML générique, qui parse du XML uploadé par un utilisateur non
fiable : jamais `xml.etree.ElementTree` nu, risque XXE/milliard de rires —
un des fixtures GDAL candidats explorés pour GML s'appelle d'ailleurs
`billionlaugh.gml`/`.xsd`, rappel direct que ce risque est réel sur ce type
d'entrée), `openpyxl>=3.1` (déjà utilisé par `parse_xlsx_latlon`).

## 2. Architecture

### 2.1 Fonction pivot `extract_geometry` + `GeometryMode`

Décision centrale du brainstorm : une fonction unique d'extraction de
géométrie, appelée par tous les nouveaux parseurs tabulaires (Excel,
Parquet non-géo, JSON Lines, CSV/WKT, XML générique aplati) — pour ne pas
dupliquer 5 fois le même choix « lat/lon vs WKT vs aucune », classe de dette
déjà payée plusieurs fois sur ce dépôt (SP-43). Alternative explicitement
écartée par Tanguy : dupliquer la logique par parseur.

```python
# core/app/ingestion/parsers.py

@dataclass(frozen=True)
class GeometryMode:
    """Résolu une fois par import (jamais recalculé ligne à ligne) — kind
    fixe la stratégie, les champs optionnels portent les noms de colonnes
    déjà résolus (auto-détection ou choix explicite de l'utilisateur, faits
    en amont par l'appelant, jamais par extract_geometry elle-même)."""

    kind: Literal["latlon", "wkt", "none"]
    lat_field: str | None = None
    lon_field: str | None = None
    wkt_field: str | None = None


def extract_geometry(row: dict, mode: GeometryMode) -> tuple[BaseGeometry | None, dict]:
    """Retourne (géométrie ou None, propriétés restantes — colonnes de
    géométrie retirées). Lève IngestionParseError sans contexte de ligne
    (l'index de ligne est ajouté par l'appelant, qui seul le connaît — cf.
    patron déjà en vigueur dans parse_csv_latlon/parse_xlsx_latlon)."""
    if mode.kind == "none":
        return None, dict(row)
    if mode.kind == "latlon":
        raw_lat, raw_lon = row.get(mode.lat_field), row.get(mode.lon_field)
        try:
            lat, lon = float(raw_lat), float(raw_lon)
        except (TypeError, ValueError):
            raise IngestionParseError(
                f"lat/lon invalide ('{raw_lat}', '{raw_lon}')"
            ) from None
        rest = {k: v for k, v in row.items() if k not in (mode.lat_field, mode.lon_field)}
        return Point(lon, lat), rest
    # mode.kind == "wkt"
    raw_wkt = row.get(mode.wkt_field)
    try:
        geom = shapely.from_wkt(raw_wkt)
    except (ShapelyError, TypeError) as exc:
        raise IngestionParseError(f"WKT invalide ('{raw_wkt}') : {exc}") from exc
    rest = {k: v for k, v in row.items() if k != mode.wkt_field}
    return geom, rest
```

Chaque appelant catche `IngestionParseError` et la re-lève avec son propre
contexte de ligne (`f"ligne {i} : {exc}"`), exactement comme
`parse_csv_latlon`/`parse_xlsx_latlon` le font déjà pour leurs propres
erreurs — pas de changement à ce patron, `extract_geometry` s'y insère.

**Auto-détection des noms de colonnes lat/lon (`detect_lat_lon_fields`,
déjà existante) reste un pré-traitement**, exécuté une fois par import par
chaque parseur avant de construire son `GeometryMode` — `extract_geometry`
elle-même ne devine jamais un nom de colonne, elle applique une stratégie déjà
résolue. C'est ce qui permet de réutiliser `detect_lat_lon_fields` telle
quelle pour CSV, XLSX, JSON Lines et Parquet non-géo sans la dupliquer.

**Refonte de signature nécessaire** (changement, pas addition, sur du code
déjà shippé par SP-6a/SP-56) :

```python
# avant
def parse_csv_latlon(content: bytes, lat_field: str | None, lon_field: str | None): ...
def parse_xlsx_latlon(content: bytes, lat_field: str | None, lon_field: str | None): ...

# après
def parse_csv_latlon(content: bytes, mode: GeometryMode) -> Iterator[tuple[BaseGeometry | None, dict]]: ...
def parse_xlsx_sheet(content: bytes, sheet_name: str | None, mode: GeometryMode) -> Iterator[tuple[BaseGeometry | None, dict]]: ...
```

`parse_xlsx_latlon` est **renommée** `parse_xlsx_sheet` (gagne
`sheet_name: str | None` — feuille explicite ou `wb.active` si `None`, pour
rester compatible avec le cas mono-feuille). Les ~15 tests existants de ces
deux fonctions (`test_ingestion_parsers.py`) doivent être réécrits pour
passer un `GeometryMode(kind="latlon", lat_field=..., lon_field=...)` au lieu
de deux positionnels — mécanique, mais réel (pas juste additif), à faire
dans la même tâche que la fonction pivot elle-même (cf. plan).

Résolution du mode pour CSV/XLSX quand l'appelant ne précise **ni** lat/lon
**ni** WKT explicitement (rétrocompatibilité du comportement actuel, jamais
cassée) : l'appelant (`run_import`) construit `GeometryMode(kind="latlon",
lat_field=None, lon_field=None)` par défaut, et `parse_csv_latlon`/
`parse_xlsx_sheet` conservent leur logique actuelle d'auto-détection
(`detect_lat_lon_fields`) **avant** d'appeler `extract_geometry` — l'API
publique HTTP ne change donc rien pour un CSV/XLSX importé exactement comme
avant SP-56/ce SP.

### 2.2 Excel multi-feuilles

`list_xlsx_sheets(content: bytes) -> list[LayerInfo]` (nouvelle fonction,
même dataclass `LayerInfo` que GPKG/KML — `name`, `feature_count`,
`geometry_type`) : énumère `wb.sheetnames`, `feature_count` = nombre de
lignes de données (à vérifier empiriquement contre la version `openpyxl`
verrouillée — `ws.max_row` est documenté comme potentiellement imprécis en
mode `read_only=True` avant itération complète ; si confirmé peu fiable,
compter par itération bornée est acceptable ici, aucun volume important
n'est visé par ce chantier), `geometry_type` = sentinelle fixe `"Tabular"`
(une feuille Excel n'a pas de type de géométrie OGC — cette valeur n'est
jamais interprétée ailleurs que par la mise en forme de l'option dans le
sélecteur, déjà `t("importFile.layerOptionTemplate", {name, count})` côté
shell, qui n'affiche pas `geometryType`).

`read_xlsx_header_fields(content: bytes, sheet_name: str | None = None)` —
signature étendue (ajout d'un paramètre optionnel, rétrocompatible) : lit
l'en-tête de la feuille nommée, ou de `wb.active` si `None` (comportement
actuel inchangé pour un classeur mono-feuille).

`inspect_upload` (routes.py) — nouvelle branche `.xlsx` :

```python
if body.filename.lower().endswith(".xlsx"):
    if body.layerName is not None:
        # 2e appel, après que l'utilisateur a choisi une feuille en
        # selecting-layer : renvoyer les colonnes de CETTE feuille.
        fields = read_xlsx_header_fields(content, sheet_name=body.layerName)
        return InspectResponse(layers=[], fields=fields)
    sheets = list_xlsx_sheets(content)
    if len(sheets) > 1:
        return InspectResponse(layers=[LayerInfoOut(...) for s in sheets])
    # classeur mono-feuille : comportement actuel inchangé
    fields = read_xlsx_header_fields(content)
    return InspectResponse(layers=[], fields=fields)
```

`InspectRequest` gagne `layerName: str | None = None` (seul champ nouveau du
contrat — `InspectResponse` n'en a besoin d'aucun, conforme à la décision).

### 2.3 Parquet non-géo

Sniff de la clé `"geo"` dans les métadonnées du fichier (spec GeoParquet
1.0, écrite par tout writer GeoParquet conforme, y compris
`app.cdc.parquet_writer.write_geoparquet` de SP-11) :

```python
def _is_geoparquet(path: str) -> bool:
    schema = pyarrow.parquet.read_schema(path)  # lit le footer, pas les données
    return b"geo" in (schema.metadata or {})
```

`run_import` sniffe **après** avoir écrit le contenu dans le fichier
temporaire déjà requis par `_temp_file(content, ".parquet")` — pas de lecture
en double. `_pick_format` seul ne peut plus décider pour `.parquet` (il ne
voit que le nom de fichier) : soit son type de retour distingue déjà les deux
cas et `run_import` fait le sniff avant d'appeler `_pick_format` pour ce cas
précis, soit (plus simple) `run_import` traite `.parquet` comme un cas à part
avant le grand `if/elif` de dispatch, en appelant `_is_geoparquet` puis
`parse_geoparquet` ou le nouveau `parse_parquet_tabular` — **cette dernière
forme est retenue** pour ne pas changer la signature de `_pick_format` pour
un seul format.

```python
def parse_parquet_tabular(content: bytes, mode: GeometryMode) -> Iterator[tuple[BaseGeometry | None, dict]]:
    with _temp_file(content, ".parquet") as path:
        table = pyarrow.parquet.read_table(path)
        for row in table.to_pylist():
            yield extract_geometry(row, mode)
```

Valeurs non scalaires (struct/liste imbriquée dans une colonne Parquet) :
sérialisées en JSON compact (`json.dumps`) avant d'être exposées comme
propriété — même traitement que JSON Lines (§2.4), pour la même raison
(`_sql_type_for` ne connaît que bool/int/float/texte).

**Contrat d'inspection pour `.parquet`** — le client ne peut pas savoir avant
upload s'il s'agit d'un GeoParquet ou d'un Parquet non-géo (seul le serveur
sniffe le contenu, §2.3 ci-dessus) ; `inspect_upload` doit donc traiter
`.parquet` de façon uniforme côté route, et distinguer les deux cas par la
**valeur** de `InspectResponse.fields` (champ déjà `list[str] | None`,
aucun changement de schéma nécessaire) :

```python
if body.filename.lower().endswith(".parquet"):
    if _is_geoparquet(path):
        # Géométrie déjà native (GeoParquet) — aucune étape de géométrie
        # à proposer. fields=None est le sentinel réutilisé (déjà la
        # valeur par défaut du schéma) pour dire « rien à choisir ici »,
        # distinct de fields=[] (fichier tabulaire sans aucune colonne,
        # cas limite valide mais différent).
        return InspectResponse(layers=[], fields=None)
    fields = read_parquet_header_fields(content)
    return InspectResponse(layers=[], fields=fields)
```

`read_parquet_header_fields(content: bytes) -> list[str]` (nouvelle
fonction, même rôle que `read_xlsx_header_fields` : lit le schéma Parquet —
`pyarrow.parquet.read_schema`, pas les données — pour lister les noms de
colonnes).

### 2.4 JSON Lines

```python
def parse_jsonlines(content: bytes, mode: GeometryMode) -> Iterator[tuple[BaseGeometry | None, dict]]:
    text = content.decode("utf-8-sig")  # cohérent avec parse_geojson/parse_csv_latlon
    for i, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestionParseError(f"ligne {i} : JSON invalide ({exc})") from exc
        if not isinstance(row, dict):
            raise IngestionParseError(f"ligne {i} : chaque ligne doit être un objet JSON")
        row = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
               for k, v in row.items()}
        try:
            yield extract_geometry(row, mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc
```

Colonnes = union des clés rencontrées sur **toutes** les lignes du fichier
(comportement déjà celui d'`importer.py`, aucun changement requis là —
seule une valeur `null` sur une ligne et présente ailleurs suit déjà la
règle existante « type déduit de la première valeur non nulle »).

**Pour `POST /uploads/inspect`** (proposer des colonnes au shell avant de
lancer le job, sans lire un fichier potentiellement volumineux en entier) :
nouvelle fonction dédiée, bornée à un échantillon :

```python
def read_jsonlines_header_fields(content: bytes, sample_lines: int = 20) -> list[str]:
    """Union des clés des N premières lignes non vides — jamais tout le
    fichier. Le job d'import réel (run_import → parse_jsonlines) traite
    lui, comme toujours, la totalité des lignes ; un champ absent de
    l'échantillon mais présent plus loin dans le fichier est simplement une
    colonne de plus, découverte par run_import au moment du job, pas ici."""
```

`inspect_upload` gagne une branche `.jsonl` symétrique de celle du XLSX
mono-feuille : retourne `InspectResponse(layers=[], fields=[...])`.

**Collision de propriété réservée, vérifiée sur le fixture réel (§5) :**
`scifact_claims.jsonl` porte une clé `id` sur chaque ligne — collision
garantie avec la colonne `id serial PRIMARY KEY` que `run_import` pose
toujours (même classe de bug que le `id` KML fermé par SP-56, cf. §1.1).
Généralisation retenue plutôt que dupliquer un correctif JSON-Lines-only :
`_rename_kml_reserved_properties`/`_KML_RESERVED_PROPERTY_NAMES` deviennent
une fonction générique parametrée par préfixe :

```python
_RESERVED_PROPERTY_NAMES = {"id", "tenant_id", "geom"}

def _rename_reserved_property_keys(props: dict, prefix: str) -> dict:
    return {
        (f"{prefix}_{key}" if key in _RESERVED_PROPERTY_NAMES else key): value
        for key, value in props.items()
    }
```

`parse_kml` est **refactorée** pour appeler `_rename_reserved_property_keys(
props, "kml")` (sortie strictement identique — `kml_id`/`kml_tenant_id`/
`kml_geom`, comme avant ; `test_parse_kml_renames_reserved_id_property`
existant doit rester vert **sans modification** — c'est la preuve que le
refactor n'a rien changé). `parse_jsonlines` applique
`_rename_reserved_property_keys(row, "jsonl")` avant `extract_geometry`.
`parse_xml_generic` (§2.6) applique la même chose avec le préfixe `"xml"`.

### 2.5 CSV/WKT

Extension de `parse_csv_latlon` (signature déjà revue en §2.1) : le mode
`GeometryMode(kind="wkt", wkt_field=...)` est résolu par l'appelant
(`run_import`, depuis `IngestionJobCreate.wktField` — nouveau champ, cf.
§2.8) exactement comme `lat_field`/`lon_field` le sont déjà. Aucune
auto-détection de colonne WKT (pas de nom conventionnel comme
`lat`/`lon` — une colonne WKT peut s'appeler n'importe quoi, `wkt`, `geom`,
`the_geom`…) : l'utilisateur choisit toujours explicitement la colonne WKT
dans l'étape `selecting-geometry` (§2.8), jamais d'auto-détection pour ce
mode. Pas de fixture réelle dédiée (cf. §5, raison explicite) : les tests
de ce mode sont des littéraux CSV inline, comme le sont déjà tous les tests
CSV existants (`test_parse_csv_latlon_*`).

### 2.6 GML/INSPIRE

```python
def parse_gml(content: bytes, layer_name: str | None = None) -> Iterator[tuple[BaseGeometry, dict]]:
    with _temp_file(content, ".gml") as path:
        for geom, props in _read_features(path, layer_name):
            yield geom, _rename_reserved_property_keys(props, "gml")
```

Pas de branche zip/kmz équivalente (un GML n'a pas d'analogue `.gmz`) — plus
simple que `parse_kml`, un seul suffixe possible. `_ALLOWED_TEMP_SUFFIXES`
gagne `.gml`. `list_layers()` (`core/app/ingestion/parsers.py`) gagne une
branche `.gml` identique à celle `.kml`/`.kmz` (pas de wrap `/vsizip/`, un
seul littéral de suffixe).

**À vérifier empiriquement pendant l'exécution du plan, pas supposé ici**
(piège CLAUDE.md n°3) : le driver GML de GDAL impose-t-il, comme le driver
KML, un champ `id` sur toute feature ? Le fixture réel retenu (§5,
`archsites.gml`) porte `gml:id` en attribut XML namespacé sur l'élément
racine de la feature, pas nécessairement exposé comme propriété `id` par
`pyogrio.raw.read` (différence de sémantique GML vs KML — le schéma GML
n'impose pas la même colonne `id` que le schéma KML). Le test
`test_parse_gml_yields_geometry_and_properties` doit vérifier le nom exact
des propriétés retournées sur ce fixture réel avant de décider si le
renommage réservé change effectivement quelque chose ici (il est appliqué
par défense en profondeur dans tous les cas — coût nul si aucune collision
ne se produit réellement).

`_pick_format` (importer.py) gagne : `.gml` → `"gml"` → `parse_gml(content,
layer_name)`.

### 2.7 XML générique

**Sécurité — obligatoire, pas une option** : parsing via
`defusedxml.ElementTree.fromstring` (déjà une dépendance du cœur, déjà
utilisée à deux autres endroits), jamais `xml.etree.ElementTree` nu — ce
parseur reçoit du XML téléversé par un utilisateur non fiable, risque XXE/
entité récursive (« milliard de rires ») réel et documenté par les propres
fixtures de test GDAL explorées pour ce chantier (`billionlaugh.gml`).

Algorithme de détection de l'« élément répété » (decision #6, aucun
mapping XPath) :

1. Parcours en largeur (BFS, ordre du document) depuis la racine.
2. Pour le premier élément visité (parent) dont les enfants directs
   contiennent un même nom de balise apparaissant **≥ 2 fois**, ce nom de
   balise devient « l'élément répété » — arrêt de la recherche à ce niveau
   (le premier niveau qualifiant gagne ; pas de recherche de tous les
   niveaux qualifiants, ni de préférence pour le niveau le plus profond —
   choix délibéré pour rester déterministe et simple, cohérent avec
   « pas d'UX riche »).
3. Les « lignes » = tous les enfants directs de CE parent portant ce nom de
   balise (pas une recherche globale dans tout le document — un seul groupe
   parent/nom, celui trouvé à l'étape 2).
4. Pour chaque ligne, colonnes = union des enfants directs qui sont des
   **feuilles texte** (l'enfant n'a lui-même aucun enfant élément — un enfant
   qui contient d'autres éléments est ignoré, pas aplati récursivement,
   conformément à la décision « aplatissement de ses enfants texte
   directs », pas plus) ; valeur = `child.text.strip()` (ou `""` si `None`).
   Les **attributs** de l'élément-ligne lui-même sont inclus comme colonnes
   supplémentaires (ex. `<book id="bk101">` → colonne `id`), car c'est un
   cas d'usage réel et fréquent (identifiants portés en attribut plutôt
   qu'en enfant texte) — sans cela, l'attribut `id` du fixture réel retenu
   (§5) serait silencieusement perdu.
5. Aucune colonne géométrique native : ce format passe toujours par
   `extract_geometry(row, mode)`, `mode` résolu comme pour JSON Lines/Parquet
   non-géo (le fixture réel retenu n'a pas de coordonnées → mode "none" en
   pratique, mais le code ne suppose rien de spécifique à ce fixture).
6. `_rename_reserved_property_keys(row, "xml")` avant `extract_geometry` —
   le fixture réel retenu porte un attribut `id` sur chaque ligne, collision
   garantie et vérifiée (pas supposée) avec la colonne `id` fixe.

```python
def parse_xml_generic(content: bytes, mode: GeometryMode) -> Iterator[tuple[BaseGeometry | None, dict]]:
    root = defusedxml.ElementTree.fromstring(content)
    parent, tag = _find_repeated_element(root)  # BFS, §étapes 1-2
    if parent is None:
        raise IngestionParseError("aucun élément répété détecté — format non reconnu")
    for i, elem in enumerate([e for e in parent if e.tag == tag], start=1):
        row: dict = dict(elem.attrib)
        for child in elem:
            if len(child) == 0:  # feuille texte, pas un sous-élément structuré
                row[_local_name(child.tag)] = (child.text or "").strip()
        row = _rename_reserved_property_keys(row, "xml")
        try:
            yield extract_geometry(row, mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc
```

`_local_name(tag)` : retire un éventuel préfixe d'espace de noms
(`{uri}local` → `local`) — `ElementTree` qualifie les tags avec l'URI complète
entre accolades dès qu'un `xmlns` est déclaré ; sans cette normalisation, une
balise `<title>` sous un document avec espace de noms produirait une colonne
nommée `{http://...}title`, illisible. Le fixture réel retenu (`books.xml`,
§5) n'a **pas** d'espace de noms déclaré — `_local_name` doit donc être testée
séparément avec un littéral XML synthétique qui EN a un, pour ne pas laisser
ce cas non couvert par le seul fixture réel.

**`.xml` vs `.gml` — désambiguïsation par extension, pas par contenu** :
un fichier `.gml` passe par `parse_gml`/GDAL (géométrie native) ; un fichier
`.xml` passe par `parse_xml_generic` (aplatissement générique, géométrie
choisie par l'utilisateur). Pas de sniff de contenu pour distinguer les
deux — cohérent avec la décision « GML/INSPIRE et XML générique sont deux
formats distincts » du brainstorm.

`_pick_format` (importer.py) gagne : `.xml` → `"xml_generic"` →
`parse_xml_generic(content, mode)`. `list_layers`/`inspect_upload` ne
traitent **pas** `.xml` comme un format à couches (un seul groupe de lignes
détecté par fichier, jamais plusieurs) — l'inspection `.xml` suit le même
chemin que JSON Lines/Parquet non-géo/CSV : `fields` seul, jamais `layers`.
`read_xml_header_fields(content) -> list[str]` (nouvelle fonction, même
rôle que `read_xlsx_header_fields`/`read_jsonlines_header_fields` : exécute
l'algorithme de détection sur un échantillon des premières lignes trouvées,
union des noms de colonnes).

### 2.8 Contrats d'API (schemas.py)

```python
class InspectRequest(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    layerName: str | None = None  # NOUVEAU — 2e appel d'inspection scopé
                                   # à une feuille XLSX déjà choisie

class IngestionJobCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    collectionTitle: str = Field(min_length=1)
    latField: str | None = None
    lonField: str | None = None
    layerName: str | None = None
    wktField: str | None = None          # NOUVEAU
    geometryMode: Literal["latlon", "wkt", "none"] | None = None  # NOUVEAU
```

`geometryMode` absent (`None`) préserve exactement le comportement actuel
(auto-détection lat/lon si `latField`/`lonField` absents aussi) — c'est
l'unique garantie de rétrocompatibilité binaire du contrat HTTP existant.
`run_import` construit le `GeometryMode` effectif :

```python
def _resolve_geometry_mode(body) -> GeometryMode:
    if body.geometryMode == "wkt":
        return GeometryMode(kind="wkt", wkt_field=body.wktField)
    if body.geometryMode == "none":
        return GeometryMode(kind="none")
    return GeometryMode(kind="latlon", lat_field=body.latField, lon_field=body.lonField)
```

`InspectResponse` : **inchangé** (`layers`/`fields` suffisent à toutes les
nouvelles formes — confirmé par la conception ci-dessus, aucun format
n'a besoin d'un troisième champ de réponse).

### 2.9 `run_import` — table sans géométrie, pas de Map créée

`_pick_format(filename)` gagne les branches `.jsonl` → `"jsonlines"`,
`.xml` → `"xml_generic"`, `.gml` → `"gml"` ; le cas `.parquet` reste détecté
par extension mais désormais désambiguïsé par sniff (§2.3) avant de choisir
`parse_geoparquet` ou `parse_parquet_tabular`.

Construction de table — changement minimal et localisé : le `geom` n'est
ajouté à `CREATE TABLE`/`INSERT` **que si au moins une géométrie non-`None`**
a été produite par le parseur. Avec `mode.kind == "none"`, toutes les lignes
ont `geom is None` par construction (un seul mode par import, jamais mixte
au sein d'un même fichier) → aucune colonne `geom`, table strictement
tabulaire — c'est exactement la forme qu'`introspect_table`/`table_extent`/
`apply_collection_ddl` savent déjà lire (§1.4).

```python
has_geometry = any(geom is not None for geom, _props in rows)
...
if has_geometry:
    create_sql += f", geom geometry({pg_geom_type}, 4326))"
else:
    create_sql += ")"
...
# idem pour insert_cols_full/values_clause : omettre "geom"/ST_GeomFromText
# quand not has_geometry.
```

**Pas de Map créée quand `not has_geometry`** — décision de scope explicite,
alignée sur le fait que `register_collection` (le flux admin existant) ne
crée déjà aucune Map pour une collection sans géométrie (§1.4) :

```python
@dataclass
class ImportResult:
    collection_id: str
    item_id: str | None  # NOUVEAU : None quand la collection n'a pas de géométrie
```

`run_import` saute intégralement le bloc `items_repo.create_item(...)` +
`configs_repo.create_config(...)` quand `not has_geometry`, retourne
`ImportResult(collection_id=col.id, item_id=None)`.

`IngestionJobStatus.itemId` est déjà `str | None` (schema inchangé) — le
job passe à `status="done"` avec `itemId=None`.

**Changement shell requis, sinon régression réelle** (piège CLAUDE.md n°4,
trouvé en concevant, pas en exécutant) : `ImportFileButton.poll()`
aujourd'hui —

```ts
if (job.status === "done" && job.itemId) { close(); navigate(`/maps/${job.itemId}`); return; }
```

— ne gère PAS `status === "done" && !job.itemId` : ce cas n'existe pas
encore dans le dépôt (`item_id` est aujourd'hui toujours non-null en sortie
de job réussi), donc ce garde-fou n'a jamais été nécessaire jusqu'ici. Ce SP
l'introduit pour la première fois → doit corriger `poll()` pour distinguer
`done` avec et sans `itemId` : sans `itemId`, fermer le tiroir et naviguer
vers `/admin/collections` (la page qui liste déjà toute collection, avec ou
sans géométrie — cohérent avec ce que `register_collection` fait déjà
atterrir aujourd'hui pour ce même cas). Sans ce correctif, un import « sans
géométrie » resterait bloqué en sondage infini (poll() boucle indéfiniment
tant que `itemId` reste falsy, jamais de sortie de boucle pour un `status
=== "done"` sans item).

## 3. Shell — machine à états `ImportFileButton.tsx`

### 3.1 Renommage de phase

`"selecting-latlon"` → `"selecting-geometry"` (le choix n'est plus limité à
lat/lon — 3 options désormais). Renommage mécanique de la valeur de type
`Phase` et de tous ses usages ; aucune clé i18n existante ne change de texte
(seuls les libellés des nouvelles options sont ajoutés).

### 3.2 Le sélecteur `selecting-geometry` à 3 options

Remplace les deux `<select>` lat/lon actuels par un choix de mode (boutons
radio ou `<select>` de mode + sous-formulaire conditionnel) :

- **lat/lon** (défaut si auto-détecté) : deux `<select>` de colonnes, comme
  aujourd'hui.
- **colonne WKT unique** : un `<select>` de colonne.
- **aucune géométrie** : aucun contrôle supplémentaire, juste une validation
  qui autorise la soumission sans colonne choisie.

`startJob()` envoie `geometryMode` + le champ pertinent (`latField`/
`lonField` OU `wktField` OU rien) selon le mode choisi dans ce sélecteur.

### 3.3 Extensions de flux existants

- `isLayeredFormat(filename)` gagne `.gml` (mêmes branches que
  gpkg/zip/kml/kmz — géométrie déjà native, aucun passage par
  `selecting-geometry` après le choix de couche).
- Nouveau prédicat côté client `needsSheetSelection(filename)` : vrai pour
  `.xlsx` uniquement — remplace `needsFieldInspection` pour ce format
  (celui-ci reste utilisé tel quel pour `.jsonl`/`.xml`/`.parquet`, qui
  n'ont jamais de concept de couche/feuille).
- Flux XLSX complet, 4 branches possibles après upload :
  1. Une seule feuille, lat/lon auto-détectés → job direct (comportement
     actuel, inchangé).
  2. Une seule feuille, lat/lon non détectés → `selecting-geometry`
     (comportement actuel étendu au 3e choix).
  3. Plusieurs feuilles → `selecting-layer` (choix de la feuille) → **2e
     appel** `inspectUpload({key, filename, layerName: <feuille choisie>})`
     → si lat/lon auto-détectés sur cette feuille, job direct ; sinon
     `selecting-geometry` scopé à cette feuille.
  4. (implicite) Le job final transporte toujours `layerName` (nom de la
     feuille) en plus du mode de géométrie choisi — `IngestionJobCreate`
     porte déjà les deux champs, aucun conflit.
- `.jsonl`/`.xml`/`.parquet` suivent le chemin déjà existant du XLSX
  mono-feuille (`needsFieldInspection` étendu à ces 3 extensions,
  `inspectUpload` sans `layerName`). **Cas particulier `.parquet`** — avant
  ce SP, un `.parquet` ne passait par **aucune** inspection (toujours
  GeoParquet supposé, `startJob` direct) ; ce SP doit l'ajouter à
  `needsFieldInspection` pour pouvoir distinguer géo/non-géo côté serveur
  (§2.3), donc **tout** `.parquet` passe désormais par `inspectUpload` avant
  le job — changement de comportement réseau (un appel HTTP de plus) mais
  pas de régression fonctionnelle pour un GeoParquet existant. Le client
  distingue les deux cas par la valeur de `fields`, pas par une nouvelle
  extension de schéma :
  ```ts
  const { fields } = await client.inspectUpload({ key, filename: file.name });
  if (fields === null) {
    // GeoParquet — géométrie déjà native, aucune étape de géométrie.
    await startJob(key, undefined);
  } else if (!detectLatLon(fields)) {
    setCsvHeaders(fields); // réutilisé tel quel pour peupler selecting-geometry
    setPhase("selecting-geometry");
  } else {
    await startJob(key, undefined);
  }
  ```
  `fields === null` (et non `fields.length === 0`) est le test exact à
  utiliser — une réponse `fields: []` (fichier tabulaire réellement sans
  colonne) doit au contraire passer par `selecting-geometry` (qui affichera
  alors 0 option, cas limite mais correct), jamais être confondue avec le
  sentinel « géométrie déjà native ».
- CSV : chemin **inchangé** au niveau de la détection (sniff navigateur avant
  upload) mais son formulaire de saisie manuelle (déjà affiché inline dans
  `form`, sans passer par `selecting-latlon`) gagne lui aussi le choix WKT —
  cohérent avec decision #4, sans introduire un flux d'inspection serveur qui
  n'existe pas aujourd'hui pour CSV.
- `accept` gagne `.jsonl,.gml,.xml` (`.parquet` déjà présent, couvre les deux
  variantes géo/non-géo — aucune distinction possible ni nécessaire côté
  `<input type="file">`).

### 3.4 Chemin de lecture — vérifier `toFrontLayer()` (piège CLAUDE.md n°5)

Ce chantier ne modifie **aucun** champ de `BuilderConfig`/`MapConfig` — il
modifie uniquement le pipeline d'ingestion et le contrat de
`POST /uploads`/`POST /uploads/inspect`. Le piège n°5 (chemin de lecture
oublié dans `toFrontLayer()`) ne s'applique donc pas directement ici ; à
confirmer en plan (tâche de revue finale) qu'aucun champ nouveau n'a été
introduit par erreur sur ces configs.

## 4. Fixtures de test réelles — sources vérifiées

Rappel de contrainte : Tanguy veut des fixtures **réellement téléchargées**
(pas des fichiers synthétiques écrits à la main), avec licence permissive
compatible Apache-2.0. Ce qui suit a été **vérifié par requête directe**
(GitHub API, `gh api`) pendant l'écriture de cette spec — existence du
fichier et licence du dépôt, pas seulement supposées :

| Format | Fichier | Dépôt source | Licence vérifiée | Taille vérifiée | Notes |
|---|---|---|---|---|---|
| GML | `autotest/ogr/data/gml/archsites.gml` | `OSGeo/gdal` | MIT (`LICENSE.TXT` racine, lu intégralement) | 1898 octets | WFS 1.1.0 `FeatureCollection`, schéma plat (`og:cat`/`og:str1`), géométrie `Point`, CRS **EPSG:26713** (non-WGS84 — exerce aussi la reprojection déjà présente dans `_read_features`), un seul type de feature (`og:archsites`) → une seule couche. |
| XLSX multi-feuilles | `test-data/spreadsheet/TwoSheetsNoneHidden.xlsx` | `apache/poi` | Apache-2.0 (`legal/LICENSE`, lu, en-tête confirmé) | 7938 octets | Nom de fichier suggère fortement 2 feuilles visibles, aucune masquée — **contenu des feuilles non prévisualisé** (fichier binaire) : à vérifier à l'exécution que les en-têtes sont exploitables ; repli documenté ci-dessous si non. |
| JSON Lines | `examples/data/scifact_claims.jsonl` | `openai/openai-cookbook` | MIT (`.license.spdx_id` de l'API dépôt) | 65007 octets | Contenu lu (2 premières lignes) : mélange de colonnes scalaires (`id` int, `claim` str) et non-scalaires (`evidence` dict, `cited_doc_ids` list) — exerce à la fois la sérialisation JSON des valeurs imbriquées (§2.4) et la collision de propriété réservée `id` (§2.4). **À tronquer aux ~10 premières lignes lors du commit du fixture** (fichier complet trop volumineux pour un fixture de test ; les 10 premières lignes suffisent à couvrir scalaire+imbriqué+collision `id`, vérifié dans les 2 lignes déjà lues). |
| XML générique | `playground/Stress/Stress.ApiService/content/books.xml` | `microsoft/aspire` | MIT (`.license.spdx_id` de l'API dépôt) | 4388 octets | Contenu lu intégralement (30 premières lignes) : `<catalog><book id="bk101">...<author>/<title>/<genre>/<price>/<publish_date>/<description></book>...</catalog>` — exemple canonique de l'heuristique « élément répété » (`book` sous `catalog`), attribut `id` sur l'élément-ligne (collision réservée vérifiée), enfants texte simples (`description` multi-lignes avec indentation, exerce `.strip()`). |
| Parquet non-géo | — | — | — | — | **Pas de fixture réelle requise** : comme les tests GeoParquet existants (SP-56), le fixture est écrit programmatiquement via `pyarrow`/`pandas` dans `tmp_path` (table sans clé `"geo"` dans les métadonnées) — format binaire trivial à générer correctement en test, aucun bénéfice à en télécharger un ; cohérent avec le patron déjà en vigueur pour `parse_geoparquet`. |
| CSV/WKT | — | — | — | — | **Pas de fixture réelle requise** : comme tous les tests CSV existants (`test_parse_csv_latlon_*`), littéraux Python inline (`"nom,wkt\nA,POINT(1 2)\n"`) — un CSV est trivialement et légitimement synthétisable, la préoccupation de Tanguy porte sur les formats dont une écriture manuelle risquerait de ne pas représenter un fichier réel (GML/XLSX/JSONL/XML), pas sur un format texte à 2 colonnes. |

**Critère de repli, explicite pour chaque fixture réelle** (à appliquer par
la session qui exécute le plan si la source ci-dessus s'avère indisponible
ou inexploitable au moment de l'exécution — ne jamais bloquer dessus) :
chercher une source équivalente sous licence MIT/Apache-2.0/CC0/domaine
public, documenter le remplacement dans le commit qui ajoute le fixture
(chemin exact, licence vérifiée, raison du remplacement). Pour le XLSX en
particulier (seul candidat dont le contenu interne n'a pas été prévisualisé
ici) : si `TwoSheetsNoneHidden.xlsx` s'avère sans en-têtes exploitables,
essayer `TwoSheetsOneHidden.xlsx` (même dépôt/licence — mais introduit alors
la question des feuilles masquées, à traiter explicitement : `wb.sheetnames`
inclut-il les feuilles masquées ? à vérifier, et si oui, décider si elles
doivent apparaître dans `list_xlsx_sheets` — par défaut, **oui**, une feuille
masquée reste une feuille valide à importer, aucune UX de filtrage n'est
dans le périmètre de ce SP) avant de chercher ailleurs.

**Emplacement de commit** : `core/tests/fixtures/ingestion/` (nouveau
répertoire — aucun fixture fichier n'existe encore pour ce module, tous les
tests SP-56 génèrent leur contenu en mémoire ou dans `tmp_path`, cf. §1).
Chaque fichier commité est lu depuis le disque par les tests
(`Path(__file__).parent / "fixtures" / "ingestion" / "..."`), **jamais**
téléchargé pendant l'exécution des tests (pas de dépendance réseau en CI,
cohérent avec le reste de la suite).

## 5. Critères d'acceptation

1. Un classeur XLSX à plusieurs feuilles visibles produit `InspectResponse.
   layers` (une entrée par feuille) ; un second appel `inspectUpload` avec
   `layerName` renvoie les `fields` de cette feuille précise ; le job
   d'import qui en résulte crée une collection dont les colonnes
   correspondent exactement aux en-têtes de la feuille choisie (pas d'une
   autre feuille du même classeur).
2. Un fichier `.parquet` sans clé `"geo"` dans ses métadonnées est importé
   comme collection tabulaire (pas d'erreur, pas de tentative de lecture via
   `parse_geoparquet`) ; un `.parquet` GeoParquet existant continue d'être
   importé exactement comme avant (`parse_geoparquet`, non touché) ;
   `POST /uploads/inspect` sur un GeoParquet renvoie `fields=None` (sentinel
   « géométrie déjà native »), sur un Parquet non-géo renvoie la liste réelle
   des colonnes — le shell ne passe par `selecting-geometry` que dans le
   second cas.
3. Un fichier `.jsonl` réel (fixture téléchargé) est importé : les colonnes
   scalaires sont typées correctement, les colonnes à valeur imbriquée
   (dict/list) sont sérialisées en texte JSON, la clé `id` du fichier ne
   provoque pas d'erreur SQL de colonne dupliquée.
4. Un CSV avec une colonne WKT unique (littéral de test) est importé sans
   colonnes lat/lon.
5. Un fichier `.gml` réel (fixture téléchargé, CRS non-WGS84) est importé
   avec reprojection correcte vers EPSG:4326, les propriétés `og:cat`/
   `og:str1` (ou noms locaux équivalents) apparaissent comme colonnes.
6. Un fichier `.xml` réel (fixture téléchargé, catalogue de livres) est
   importé : l'élément répété `book` est détecté, ses enfants texte
   deviennent des colonnes, son attribut `id` ne provoque pas de collision
   SQL.
7. Un import en mode « aucune géométrie » (n'importe quel format tabulaire)
   produit une collection sans colonne `geom`, visible et listée par
   `GET /collections`/`/admin/collections`, lisible par `GET
   /collections/{id}/items` (OGC API Features, sans coordonnées) ; **aucun**
   Item/Config `kind="map"` n'est créé ; `ImportFileButton` ferme le tiroir
   et navigue vers `/admin/collections` sans rester bloqué en sondage.
8. Tous les tests existants de `parse_csv_latlon`/`parse_xlsx_latlon` (SP-6a/
   SP-56) passent après la refonte de signature, avec un comportement
   observable strictement identique (rétrocompatibilité du contrat HTTP,
   §2.1/§2.8).
9. `test_parse_kml_renames_reserved_id_property` (SP-56) passe sans
   modification après le refactor de généralisation (§2.4) — preuve que le
   comportement KML n'a pas changé.
10. Diff `openapi.json`/`core-schema.d.ts` régénéré et non vide, cohérent
    avec les 4 champs ajoutés (`InspectRequest.layerName`,
    `IngestionJobCreate.wktField`/`geometryMode`) — aucune route nouvelle,
    seulement des schémas étendus.
11. Suite complète (`core` + `shell`) verte, `ruff`/`mypy --strict`/
    `lint-imports` verts, couverture non régressive.
12. `docs/revue/inventaire-fonctionnalites.jsonl` : aucune nouvelle ligne
    requise (aucune route REST/outil MCP/route shell nouvelle — uniquement
    des formats supplémentaires sur une route déjà inventoriée,
    `POST /uploads`/`POST /uploads/inspect`) ; à confirmer néanmoins en fin
    de plan que `core/tests/test_feature_inventory.py` reste vert (aucune
    nouvelle surface détectée par erreur par son AST).

## 6. Hors périmètre explicite

- **Mapping XPath configurable** pour le XML générique — jugé disproportionné
  vu l'absence de cas d'usage concret ; l'heuristique d'élément répété est
  l'unique mécanisme, pas une option parmi d'autres.
- **Support INSPIRE dédié** (validation de schéma GML Application Schema,
  extraction de métadonnées INSPIRE spécifiques, gestion des espaces de noms
  `inspire_*`) — un GML INSPIRE est traité à l'identique de n'importe quel
  autre GML, aucune logique de schéma n'est écrite. Les fixtures
  `inspire_*.xml` du dépôt GDAL explorées en recherche (§4) ne sont
  volontairement **pas** retenues (trop complexes/schema-driven pour ce
  périmètre) au profit d'`archsites.gml`, plus simple.
- **Collision générale `id`/`tenant_id`/`geom`** pour les formats où une telle
  collision n'est ni garantie par le format (comme KML/possiblement GML) ni
  vérifiée par le fixture réel choisi (comme JSON Lines/XML générique) :
  CSV/XLSX/Parquet non-géo/GeoJSON continuent de ne PAS renommer ces
  propriétés si un utilisateur les nomme ainsi de son propre chef — gap
  pré-existant, documenté par `importer.py` depuis SP-6a, **non fermé** par
  ce SP au-delà des deux formats où la collision est vérifiée réelle.
- **Rendu carte pour une collection sans géométrie** — aucun widget carte,
  aucune UX de « table brute » dédiée n'est ajoutée ; la collection reste
  consultable seulement via `/admin/collections` et l'API OGC Features brute
  (déjà capable de la servir, §1.4). Un futur widget « table » no-code reste
  un chantier distinct, non ouvert ici.
- **Feuilles Excel masquées** — si `wb.sheetnames` les inclut (à vérifier),
  elles sont traitées comme n'importe quelle autre feuille ; aucun filtre ni
  indicateur visuel « masquée » n'est ajouté à `selecting-layer`.
- **Volumes importants** (fichiers de plusieurs centaines de Mo/millions de
  lignes) — ce chantier vise l'anticipation générique, pas la performance à
  grande échelle ; aucun test de charge n'est ajouté au-delà de ce que la
  suite existante couvre déjà pour les formats SP-6a/SP-56.
- **Deuxième langue/locale, pluralisation** des nouveaux libellés
  `selecting-geometry` — français seul, cohérent avec la décision figée
  SP-29a.
- **Un mode `--check` de fraîcheur** pour le bilan de fonctionnalités
  (SP-61, `REV-180`) — sans rapport avec ce chantier, non traité ici.
