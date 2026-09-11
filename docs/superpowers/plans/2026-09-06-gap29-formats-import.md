# GAP-29 — Formats d'import supplémentaires : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer GAP-29 : ajouter 6 formats d'import (Excel multi-feuilles,
Parquet non-géo, JSON Lines, CSV/WKT, GML/INSPIRE, XML générique) au pipeline
d'ingestion existant (`core/app/ingestion/`), via une fonction pivot partagée
d'extraction de géométrie (`extract_geometry`/`GeometryMode`), et étendre
`ImportFileButton.tsx` (shell) pour piloter les nouveaux flux sans nouvelle UX
riche.

**Architecture:** 13 tâches. Task 1 télécharge et commite les fixtures réelles
(GML/XLSX/JSONL/XML). Task 2 pose la fonction pivot `GeometryMode`/
`extract_geometry`, sans laquelle aucun parseur tabulaire (Excel, Parquet
non-géo, JSON Lines, CSV/WKT, XML générique) ne peut être écrit. Tasks 3-4
refondent les signatures CSV/XLSX existantes vers `GeometryMode` (mécanique
mais réel, casse la rétrocompatibilité de signature Python — pas du contrat
HTTP) et ajoutent CSV/WKT. Task 5 ajoute le multi-feuilles Excel. Task 6
généralise le renommage de propriété réservée (KML) avant que JSON Lines/XML
générique/GML n'en aient besoin. Tasks 7-10 ajoutent GML, JSON Lines, Parquet
non-géo, XML générique — chacune isolée à `parsers.py` + sa branche
`inspect_upload`, testée par appel direct au parseur (pas par HTTP). Task 11
câble tout dans `run_import`/`IngestionJobCreate` (dispatch complet, table
sans géométrie, pas de Map créée). Task 12 réécrit la machine à états
`ImportFileButton.tsx`. Task 13 clôture (OpenAPI/TS, inventaire de
fonctionnalités, suites complètes, `CLAUDE.md`).

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / pyogrio / geopandas /
pyarrow / openpyxl / defusedxml / shapely (cœur), React/TypeScript/Vitest/
Playwright (shell), pytest.

**Document source :**
`docs/superpowers/specs/2026-09-06-gap29-formats-import-design.md` (toutes
les sections référencées ci-dessous, `§N`, pointent vers ce document).

## Global Constraints

- **TDD strict** : chaque nouvelle fonction a son test écrit et vérifié rouge
  avant l'implémentation (`pytest ... -v`, lire "FAIL"/l'erreur exacte avant
  d'écrire le code).
- **Rétrocompatibilité du contrat HTTP** : aucun test existant de
  `POST /uploads`/`POST /uploads/inspect` ne doit changer de comportement
  observable pour GeoJSON/CSV lat-lon/XLSX mono-feuille/GPKG/Shapefile/KML/
  KMZ/GeoParquet déjà couverts par SP-6a/SP-56 — seules les signatures
  Python internes changent (§2.1 de la spec).
- **`test_parse_kml_renames_reserved_id_property` (SP-56) doit rester vert
  sans modification** après la Task 6 (généralisation du renommage réservé)
  — c'est la preuve que le refactor n'a rien changé pour KML.
- **Aucune dépendance nouvelle** : `pyarrow`, `geopandas`, `openpyxl`,
  `defusedxml` sont déjà dans `core/pyproject.toml` (§1.5 de la spec).
- **Sécurité XML** : tout parsing XML non géré par GDAL (le parseur générique,
  Task 10) utilise `defusedxml.ElementTree`, jamais `xml.etree.ElementTree`
  nu — risque XXE réel sur du contenu uploadé par un utilisateur non fiable.
- **Aucun fixture téléchargé pendant l'exécution des tests** — tout fixture
  réel est téléchargé une fois par la Task 1, commité dans
  `core/tests/fixtures/ingestion/`, lu depuis le disque par les tests
  ensuite (aucune dépendance réseau en CI).
- **Commits conventional, français, un sujet par commit**
  (`feat(core): ...`, `test(core): ...`, `refactor(core): ...`,
  `feat(shell): ...`).
- **Suite complète rejouée en fin de plan** (Task 13) : `cd core && uv run
  pytest`, `cd shell && npm run test`, `npm run e2e` si pertinent,
  `ruff`/`mypy --strict`/`lint-imports`, régénération OpenAPI/TS.

---

## Task 1 : télécharger et commiter les fixtures réelles

**Files:**
- Create: `core/tests/fixtures/ingestion/archsites.gml`
- Create: `core/tests/fixtures/ingestion/TwoSheetsNoneHidden.xlsx`
- Create: `core/tests/fixtures/ingestion/scifact_claims_sample.jsonl`
- Create: `core/tests/fixtures/ingestion/books.xml`
- Create: `core/tests/fixtures/ingestion/README.md` (provenance + licence de
  chaque fichier)

**Interfaces:**
- Produces: 4 fichiers fixtures lisibles par `Path(__file__).parent /
  "fixtures" / "ingestion" / "<nom>"` depuis n'importe quel test de
  `core/tests/test_ingestion_parsers.py`.

- [ ] **Step 1 : créer le répertoire et télécharger le fixture GML**

```bash
mkdir -p core/tests/fixtures/ingestion
curl -sL \
  https://raw.githubusercontent.com/OSGeo/gdal/master/autotest/ogr/data/gml/archsites.gml \
  -o core/tests/fixtures/ingestion/archsites.gml
wc -c core/tests/fixtures/ingestion/archsites.gml
```

Attendu : ~1898 octets (vérifié pendant l'écriture de la spec, §5 du
document source). Si la taille diverge significativement ou si le
téléchargement échoue (404, dépôt renommé/déplacé) : chercher un autre
fichier `.gml` simple et plat sous `autotest/ogr/data/gml/` du même dépôt
(`gh api repos/OSGeo/gdal/contents/autotest/ogr/data/gml --jq '.[].name'`),
éviter `gmlas_*`/`inspire_*`/`billionlaugh*` (schema-driven ou hostiles),
documenter le remplacement dans le commit et dans le README de Step 5.

- [ ] **Step 2 : télécharger le fixture XLSX**

```bash
curl -sL \
  https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/TwoSheetsNoneHidden.xlsx \
  -o core/tests/fixtures/ingestion/TwoSheetsNoneHidden.xlsx
wc -c core/tests/fixtures/ingestion/TwoSheetsNoneHidden.xlsx
```

Attendu : ~7938 octets. Puis vérifier le contenu réel (jamais prévisualisé
avant l'exécution, cf. spec §5) :

```bash
cd core && uv run python3 -c "
from openpyxl import load_workbook
wb = load_workbook('tests/fixtures/ingestion/TwoSheetsNoneHidden.xlsx', read_only=True, data_only=True)
print('sheets:', wb.sheetnames)
for name in wb.sheetnames:
    ws = wb[name]
    rows = list(ws.iter_rows(max_row=3, values_only=True))
    print(name, '->', rows)
"
```

Attendu : au moins 2 feuilles listées, chacune avec un en-tête exploitable
(des chaînes non vides sur la première ligne). Si une feuille n'a pas
d'en-tête exploitable (toutes les cellules `None`/vides) ou si le fichier
n'a qu'une seule feuille malgré son nom : essayer
`TwoSheetsOneHidden.xlsx` du même dépôt/chemin (attention alors : vérifier
si `wb.sheetnames` inclut la feuille masquée — si oui, la conserver telle
quelle, aucun filtre à ajouter, cf. spec §5/§6) ; si aucun des deux ne
convient, chercher un autre fichier `*.xlsx` sous
`test-data/spreadsheet/` du même dépôt dont le nom suggère 2+ feuilles
(`gh api repos/apache/poi/contents/test-data/spreadsheet --jq
'.[].name' | grep -iE "sheet|multi|tab"`). Documenter tout remplacement.

- [ ] **Step 3 : télécharger et tronquer le fixture JSON Lines**

```bash
curl -sL \
  https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/data/scifact_claims.jsonl \
  -o /tmp/scifact_claims_full.jsonl
head -n 10 /tmp/scifact_claims_full.jsonl > core/tests/fixtures/ingestion/scifact_claims_sample.jsonl
wc -l core/tests/fixtures/ingestion/scifact_claims_sample.jsonl
```

Attendu : 10 lignes. Vérifier que le fichier tronqué reste du JSON Lines
valide ligne par ligne :

```bash
cd core && uv run python3 -c "
import json
with open('tests/fixtures/ingestion/scifact_claims_sample.jsonl') as f:
    rows = [json.loads(line) for line in f if line.strip()]
print(len(rows), 'lignes')
print(rows[0].keys())
assert any(isinstance(v, (dict, list)) for r in rows for v in r.values()), 'aucune valeur imbriquée dans l\'échantillon'
assert any('id' in r for r in rows), 'aucune collision id dans l\'échantillon'
print('OK : scalaire + imbriqué + collision id présents')
"
```

Si l'assertion échoue (l'échantillon tronqué à 10 lignes a perdu la
diversité de colonnes) : augmenter `head -n 10` à `head -n 30` et
retronquer, en gardant le fichier aussi court que possible tout en
satisfaisant les deux assertions. Si l'URL est indisponible : chercher un
autre fixture JSON Lines réel sous licence MIT/Apache/CC0 (le repli
générique documenté par la spec §5 — ne jamais synthétiser un JSON Lines à
la main pour ce fixture précis).

- [ ] **Step 4 : télécharger le fixture XML générique**

```bash
curl -sL \
  https://raw.githubusercontent.com/microsoft/aspire/main/playground/Stress/Stress.ApiService/content/books.xml \
  -o core/tests/fixtures/ingestion/books.xml
wc -c core/tests/fixtures/ingestion/books.xml
cat core/tests/fixtures/ingestion/books.xml | head -20
```

Attendu : ~4388 octets, structure `<catalog><book id="bk101">...`. Si
l'URL est indisponible ou le chemin a bougé (le dépôt `microsoft/aspire`
est actif, son arborescence peut changer) : rechercher `books.xml` dans un
autre dépôt MIT/Apache reconnu (`gh api -X GET search/code -f
q='filename:books.xml catalog'`), en excluant tout dépôt sans licence
claire, documenter le remplacement.

- [ ] **Step 5 : documenter la provenance (obligatoire, pas un détail)**

Créer `core/tests/fixtures/ingestion/README.md` :

```markdown
# Fixtures d'ingestion — provenance et licence

Chaque fichier de ce répertoire est un téléchargement réel (pas un fichier
synthétique), conservé pour test uniquement (GAP-29).

- `archsites.gml` — OSGeo/gdal, `autotest/ogr/data/gml/archsites.gml`,
  licence MIT (`LICENSE.TXT` racine du dépôt).
- `TwoSheetsNoneHidden.xlsx` — apache/poi,
  `test-data/spreadsheet/TwoSheetsNoneHidden.xlsx`, licence Apache-2.0
  (`legal/LICENSE`).
- `scifact_claims_sample.jsonl` — openai/openai-cookbook,
  `examples/data/scifact_claims.jsonl`, licence MIT — tronqué aux N
  premières lignes (fichier source : 65 007 octets, bien plus volumineux
  qu'un fixture de test n'a besoin de l'être).
- `books.xml` — microsoft/aspire,
  `playground/Stress/Stress.ApiService/content/books.xml`, licence MIT.

Si un remplacement a eu lieu pendant l'exécution du plan (source
indisponible), la ligne correspondante ci-dessus doit être mise à jour avec
le chemin/dépôt/licence réels utilisés.
```

Si un remplacement a eu lieu à une étape précédente, mettre à jour la ligne
correspondante avec la source réelle utilisée avant de commiter.

- [ ] **Step 6 : commit**

```bash
git add core/tests/fixtures/ingestion/
git commit -m "test(core): ajoute les fixtures réelles d'import (GAP-29)"
```

---

## Task 2 : fonction pivot `GeometryMode`/`extract_geometry`

**Files:**
- Modify: `core/app/ingestion/parsers.py` (ajouter en haut du fichier, après
  les imports existants et avant `detect_lat_lon_fields`, L46)
- Test: `core/tests/test_ingestion_parsers.py` (nouveau bloc de tests, en
  tête de fichier après les imports existants)

**Interfaces:**
- Produces: `GeometryMode` (dataclass, champs `kind: Literal["latlon",
  "wkt", "none"]`, `lat_field: str | None = None`, `lon_field: str | None =
  None`, `wkt_field: str | None = None`) ; `extract_geometry(row: dict,
  mode: GeometryMode) -> tuple[BaseGeometry | None, dict]`. Consommé par
  Tasks 3-10.

- [ ] **Step 1 : écrire les tests (avant le code)**

Ajouter à `core/tests/test_ingestion_parsers.py` (après les imports, avant
`class`/`def` existants) :

```python
from app.ingestion.parsers import GeometryMode, extract_geometry


def test_extract_geometry_latlon_mode():
    geom, props = extract_geometry(
        {"lat": "48.85", "lon": "2.35", "name": "Paris"},
        GeometryMode(kind="latlon", lat_field="lat", lon_field="lon"),
    )
    assert geom.equals(Point(2.35, 48.85))
    assert props == {"name": "Paris"}


def test_extract_geometry_latlon_mode_invalid_value_fails_fast():
    with pytest.raises(IngestionParseError, match="lat/lon invalide"):
        extract_geometry(
            {"lat": "not-a-number", "lon": "2.35"},
            GeometryMode(kind="latlon", lat_field="lat", lon_field="lon"),
        )


def test_extract_geometry_wkt_mode():
    geom, props = extract_geometry(
        {"wkt": "POINT (2.35 48.85)", "name": "Paris"},
        GeometryMode(kind="wkt", wkt_field="wkt"),
    )
    assert geom.equals(Point(2.35, 48.85))
    assert props == {"name": "Paris"}


def test_extract_geometry_wkt_mode_invalid_value_fails_fast():
    with pytest.raises(IngestionParseError, match="WKT invalide"):
        extract_geometry({"wkt": "NOT WKT"}, GeometryMode(kind="wkt", wkt_field="wkt"))


def test_extract_geometry_none_mode_keeps_all_properties():
    geom, props = extract_geometry(
        {"name": "Paris", "population": 2148000},
        GeometryMode(kind="none"),
    )
    assert geom is None
    assert props == {"name": "Paris", "population": 2148000}
```

(`pytest`/`Point`/`IngestionParseError` déjà importés en tête du fichier
de test existant — vérifier avant d'ajouter un import dupliqué.)

- [ ] **Step 2 : lancer les tests, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k extract_geometry -v
```

Attendu : `ImportError: cannot import name 'GeometryMode'` (ou
`extract_geometry`) — les deux n'existent pas encore.

- [ ] **Step 3 : implémenter `GeometryMode`/`extract_geometry`**

Dans `core/app/ingestion/parsers.py`, ajouter après la ligne 52
(`detect_lat_lon_fields`) et avant `parse_geojson` (L55) :

```python
from typing import Literal


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
    géométrie retirées). Lève IngestionParseError sans contexte de ligne :
    l'appelant (qui seul connaît l'index de ligne) re-lève avec son propre
    contexte, cf. parse_csv_latlon/parse_xlsx_sheet."""
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

`Literal` n'est pas encore importé dans `parsers.py` — ajouter `from typing
import Literal` en tête du fichier (dans le bloc d'imports stdlib existant,
avec `datetime`/`io`/`json`, avant `math`).

- [ ] **Step 4 : lancer les tests, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k extract_geometry -v
```

Attendu : 5 passed.

- [ ] **Step 5 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py
git commit -m "feat(core): ajoute la fonction pivot extract_geometry/GeometryMode (GAP-29)"
```

---

## Task 3 : refonte `parse_csv_latlon` + CSV/WKT

**Files:**
- Modify: `core/app/ingestion/parsers.py:87-130` (`parse_csv_latlon`)
- Modify: `core/tests/test_ingestion_parsers.py` (réécrire les tests
  `test_parse_csv_latlon_*` existants, lignes ~75-142 avant cette tâche —
  relire le fichier réel avant d'éditer, les numéros de ligne auront déjà
  bougé après la Task 2)

**Interfaces:**
- Consumes: `GeometryMode`, `extract_geometry` (Task 2).
- Produces: `parse_csv_latlon(content: bytes, mode: GeometryMode) ->
  Iterator[tuple[BaseGeometry | None, dict]]` (signature changée — les
  appelants de Task 11 utiliseront cette forme).

- [ ] **Step 1 : réécrire les tests existants avec la nouvelle signature**

Remplacer chaque appel `parse_csv_latlon(content, lat_field, lon_field)`
par `parse_csv_latlon(content, GeometryMode(kind="latlon",
lat_field=lat_field, lon_field=lon_field))` dans
`test_parse_csv_latlon_auto_detects_columns`,
`test_parse_csv_latlon_uses_explicit_field_names`,
`test_parse_csv_latlon_fails_fast_on_invalid_row`,
`test_parse_csv_latlon_raises_when_columns_cannot_be_detected`,
`test_parse_csv_latlon_rejects_non_utf8_content`,
`test_parse_csv_latlon_wraps_oversized_field_error`. Pour
`test_parse_csv_latlon_auto_detects_columns`/
`test_parse_csv_latlon_raises_when_columns_cannot_be_detected` (qui
appellent aujourd'hui avec `lat_field=None, lon_field=None` pour déclencher
l'auto-détection), utiliser `GeometryMode(kind="latlon", lat_field=None,
lon_field=None)` — l'auto-détection doit rester déclenchée par ces valeurs
`None`, pas par une absence de mode.

Ajouter les tests CSV/WKT (nouveaux) :

```python
def test_parse_csv_latlon_wkt_mode_yields_geometry():
    content = b"name,wkt\nA,POINT (1 2)\nB,POINT (3 4)\n"
    rows = list(
        parse_csv_latlon(content, GeometryMode(kind="wkt", wkt_field="wkt"))
    )
    assert len(rows) == 2
    assert rows[0][0].equals(Point(1, 2))
    assert rows[0][1] == {"name": "A"}


def test_parse_csv_latlon_wkt_mode_invalid_wkt_fails_fast():
    content = b"name,wkt\nA,NOT WKT\n"
    with pytest.raises(IngestionParseError, match="ligne 1"):
        list(parse_csv_latlon(content, GeometryMode(kind="wkt", wkt_field="wkt")))


def test_parse_csv_latlon_none_mode_yields_no_geometry():
    content = b"name,value\nA,1\nB,2\n"
    rows = list(parse_csv_latlon(content, GeometryMode(kind="none")))
    assert len(rows) == 2
    assert rows[0][0] is None
    assert rows[0][1] == {"name": "A", "value": "1"}
```

- [ ] **Step 2 : lancer les tests, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k parse_csv_latlon -v
```

Attendu : échecs sur les tests réécrits (`TypeError: parse_csv_latlon()
takes 3 positional arguments but ... given` ou équivalent — la fonction
attend encore `lat_field, lon_field`), et `NameError`/`ImportError` sur les
3 nouveaux tests WKT (aucun mode `"wkt"`/`"none"` géré par l'implémentation
actuelle).

- [ ] **Step 3 : réécrire `parse_csv_latlon`**

Remplacer entièrement la fonction (L87-130 de `core/app/ingestion/parsers.py`
avant cette tâche) par :

```python
def parse_csv_latlon(
    content: bytes,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    try:
        fieldnames = reader.fieldnames or []
    except csv.Error as exc:
        raise IngestionParseError("en-tête CSV invalide ou mal formé") from exc
    effective_mode = mode
    if mode.kind == "latlon" and (mode.lat_field is None or mode.lon_field is None):
        detected = detect_lat_lon_fields(fieldnames)
        if detected is None:
            raise IngestionParseError(
                "colonnes lat/lon introuvables automatiquement — précisez-les"
            )
        lat_field, lon_field = detected
        effective_mode = GeometryMode(kind="latlon", lat_field=lat_field, lon_field=lon_field)
    if effective_mode.kind == "latlon" and (
        effective_mode.lat_field not in fieldnames or effective_mode.lon_field not in fieldnames
    ):
        raise IngestionParseError(
            f"colonnes '{effective_mode.lat_field}'/'{effective_mode.lon_field}' "
            "absentes du CSV"
        )
    i = 0
    row_iter = iter(reader)
    while True:
        try:
            row = next(row_iter)
        except StopIteration:
            break
        except csv.Error as exc:
            raise IngestionParseError(
                f"ligne {i + 1} : champ CSV trop volumineux ou mal formé"
            ) from exc
        i += 1
        try:
            yield extract_geometry(row, effective_mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc
```

- [ ] **Step 4 : lancer les tests, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k parse_csv_latlon -v
```

Attendu : tous passed (existants réécrits + 3 nouveaux WKT).

- [ ] **Step 5 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py
git commit -m "refactor(core): parse_csv_latlon utilise GeometryMode, ajoute le mode WKT (GAP-29)"
```

---

## Task 4 : refonte `parse_xlsx_latlon` → `parse_xlsx_sheet`

**Files:**
- Modify: `core/app/ingestion/parsers.py:139-199` (`parse_xlsx_latlon`,
  `read_xlsx_header_fields`)
- Modify: `core/tests/test_ingestion_parsers.py` (réécrire les tests
  `test_parse_xlsx_latlon_*` existants)

**Interfaces:**
- Consumes: `GeometryMode`, `extract_geometry` (Task 2).
- Produces: `parse_xlsx_sheet(content: bytes, sheet_name: str | None, mode:
  GeometryMode) -> Iterator[tuple[BaseGeometry | None, dict]]` (renommée,
  gagne `sheet_name`) ; `read_xlsx_header_fields(content: bytes, sheet_name:
  str | None = None) -> list[str]` (signature étendue, rétrocompatible).
  Consommé par Task 5 (multi-feuilles) et Task 11 (intégration).

- [ ] **Step 1 : réécrire les tests existants**

Remplacer chaque appel `parse_xlsx_latlon(content, lat_field, lon_field)`
par `parse_xlsx_sheet(content, None, GeometryMode(kind="latlon",
lat_field=lat_field, lon_field=lon_field))` dans
`test_parse_xlsx_latlon_auto_detects_columns`,
`test_parse_xlsx_latlon_uses_explicit_field_names`,
`test_parse_xlsx_latlon_raises_when_columns_cannot_be_detected`,
`test_parse_xlsx_latlon_fails_fast_on_invalid_row`,
`test_parse_xlsx_latlon_serializes_datetime_property_to_iso_string`,
`test_parse_xlsx_latlon_empty_cell_becomes_none_property`,
`test_parse_xlsx_latlon_corrupted_file_raises_parse_error`. Renommer ces 7
tests en `test_parse_xlsx_sheet_*` (cohérence avec le nouveau nom de
fonction). Ajouter un import `from app.ingestion.parsers import
parse_xlsx_sheet` (remplace `parse_xlsx_latlon` dans les imports du fichier
de test).

- [ ] **Step 2 : lancer les tests, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k parse_xlsx -v
```

Attendu : `ImportError: cannot import name 'parse_xlsx_sheet'`.

- [ ] **Step 3 : réécrire `parse_xlsx_latlon` en `parse_xlsx_sheet`**

Remplacer la fonction (L139-181 avant cette tâche) :

```python
def parse_xlsx_sheet(
    content: bytes,
    sheet_name: str | None,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except _XLSX_ERRORS as exc:
        raise IngestionParseError(f"fichier XLSX illisible : {exc}") from exc
    ws = wb[sheet_name] if sheet_name is not None else wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise IngestionParseError("classeur XLSX vide") from None
    fieldnames = [str(name) if name is not None else "" for name in header_row]
    effective_mode = mode
    if mode.kind == "latlon" and (mode.lat_field is None or mode.lon_field is None):
        detected = detect_lat_lon_fields(fieldnames)
        if detected is None:
            raise IngestionParseError(
                "colonnes lat/lon introuvables automatiquement — précisez-les"
            )
        lat_field, lon_field = detected
        effective_mode = GeometryMode(kind="latlon", lat_field=lat_field, lon_field=lon_field)
    if effective_mode.kind == "latlon" and (
        effective_mode.lat_field not in fieldnames or effective_mode.lon_field not in fieldnames
    ):
        raise IngestionParseError(
            f"colonnes '{effective_mode.lat_field}'/'{effective_mode.lon_field}' "
            "absentes du XLSX"
        )
    for i, row in enumerate(rows_iter, start=1):
        row_dict = {
            name: _xlsx_cell_value(row[j] if j < len(row) else None)
            for j, name in enumerate(fieldnames)
        }
        try:
            yield extract_geometry(row_dict, effective_mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc
```

Puis étendre `read_xlsx_header_fields` (L184-199 avant cette tâche) :

```python
def read_xlsx_header_fields(content: bytes, sheet_name: str | None = None) -> list[str]:
    """Lit uniquement la première ligne (en-têtes) d'une feuille XLSX, sans
    charger tout le classeur — utilisé par POST /uploads/inspect. `sheet_name`
    précise la feuille (2e appel d'inspection après choix en selecting-layer,
    cf. Task 5) ; None lit la feuille active (comportement mono-feuille
    inchangé)."""
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except _XLSX_ERRORS as exc:
        raise IngestionParseError(f"fichier XLSX illisible : {exc}") from exc
    ws = wb[sheet_name] if sheet_name is not None else wb.active
    try:
        header_row = next(ws.iter_rows(max_row=1, values_only=True))
    except StopIteration:
        raise IngestionParseError("classeur XLSX vide") from None
    return [str(name) if name is not None else "" for name in header_row]
```

**Attention** : la version précédente de `parse_xlsx_latlon` gardait
`lat_idx`/`lon_idx` pour exclure ces deux colonnes du dict de propriétés
*avant* de les yield-er ; la nouvelle version construit `row_dict` avec
**toutes** les colonnes puis laisse `extract_geometry` retirer lat/lon (ou
wkt, ou rien) — c'est `extract_geometry` qui porte désormais cette
responsabilité, pas le parseur. Vérifier par les tests que le comportement
observable (propriétés sans lat/lon dans le dict final) est identique.

- [ ] **Step 4 : lancer les tests, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "parse_xlsx or xlsx_sheet" -v
```

Attendu : tous passed.

- [ ] **Step 5 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py
git commit -m "refactor(core): renomme parse_xlsx_latlon en parse_xlsx_sheet, utilise GeometryMode (GAP-29)"
```

---

## Task 5 : Excel multi-feuilles

**Files:**
- Modify: `core/app/ingestion/parsers.py` (ajouter `list_xlsx_sheets`, après
  `read_xlsx_header_fields`)
- Modify: `core/app/ingestion/schemas.py:35-37` (`InspectRequest` gagne
  `layerName`)
- Modify: `core/app/ingestion/routes.py:77-109` (`inspect_upload`, branche
  `.xlsx`)
- Test: `core/tests/test_ingestion_parsers.py` (tests `list_xlsx_sheets`)
- Test: `core/tests/test_ingestion_routes.py` (tests de la branche `.xlsx`
  de `inspect_upload` — lire le fichier existant d'abord pour reprendre son
  patron de mock/fixture HTTP)

**Interfaces:**
- Consumes: `LayerInfo` (dataclass déjà existante, `parsers.py:202-206`),
  `read_xlsx_header_fields(content, sheet_name)` (Task 4).
- Produces: `list_xlsx_sheets(content: bytes) -> list[LayerInfo]`.

- [ ] **Step 1 : écrire le test de `list_xlsx_sheets` (fixture réelle,
  Task 1)**

```python
from pathlib import Path

_FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"


def test_list_xlsx_sheets_multi_sheet_workbook():
    content = (_FIXTURES / "TwoSheetsNoneHidden.xlsx").read_bytes()
    sheets = list_xlsx_sheets(content)
    assert len(sheets) >= 2
    assert all(s.geometry_type == "Tabular" for s in sheets)
    assert all(s.feature_count >= 0 for s in sheets)


def test_list_xlsx_sheets_single_sheet_workbook_returns_one_entry(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["name", "value"])
    wb.active.append(["A", 1])
    path = tmp_path / "single.xlsx"
    wb.save(path)
    sheets = list_xlsx_sheets(path.read_bytes())
    assert len(sheets) == 1
```

- [ ] **Step 2 : lancer les tests, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k list_xlsx_sheets -v
```

Attendu : `NameError`/`ImportError: cannot import name 'list_xlsx_sheets'`.

- [ ] **Step 3 : implémenter `list_xlsx_sheets`**

Ajouter après `read_xlsx_header_fields` dans `core/app/ingestion/parsers.py` :

```python
def list_xlsx_sheets(content: bytes) -> list[LayerInfo]:
    """Une entrée par feuille du classeur — même dataclass LayerInfo que
    GPKG/KML, pour réutiliser telle quelle la phase selecting-layer côté
    shell (GAP-29). geometry_type="Tabular" : une feuille Excel n'a pas de
    type de géométrie OGC, cette valeur n'est jamais interprétée ailleurs
    que par le libellé de l'option dans le sélecteur (qui n'affiche pas
    geometryType)."""
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except _XLSX_ERRORS as exc:
        raise IngestionParseError(f"fichier XLSX illisible : {exc}") from exc
    sheets = []
    for name in wb.sheetnames:
        ws = wb[name]
        # ws.max_row peut être imprécis en mode read_only avant itération
        # complète (comportement documenté d'openpyxl) — compter par
        # itération plutôt que faire confiance à max_row, aucun volume
        # important n'est visé par ce chantier (GAP-29, anticipation
        # générique).
        row_count = sum(1 for _ in ws.iter_rows(values_only=True))
        feature_count = max(row_count - 1, 0)  # moins la ligne d'en-tête
        sheets.append(LayerInfo(name=str(name), feature_count=feature_count, geometry_type="Tabular"))
    return sheets
```

- [ ] **Step 4 : lancer les tests, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k list_xlsx_sheets -v
```

Attendu : 2 passed.

- [ ] **Step 5 : ajouter `layerName` à `InspectRequest`**

Dans `core/app/ingestion/schemas.py`, remplacer :

```python
class InspectRequest(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
```

par :

```python
class InspectRequest(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    layerName: str | None = None
```

- [ ] **Step 6 : écrire les tests de la branche `.xlsx` de `inspect_upload`**

Lire d'abord `core/tests/test_ingestion_routes.py` en entier pour reprendre
le patron exact de mock du client S3/de la session (fixtures partagées du
fichier). Ajouter :

```python
def test_inspect_upload_xlsx_multi_sheet_returns_layers(client, s3_stub, ...):
    # reprendre le patron d'upload existant du fichier (upload du contenu
    # via s3_stub, puis appel POST /uploads/inspect avec filename se
    # terminant par .xlsx dont le contenu est TwoSheetsNoneHidden.xlsx)
    ...
    response = client.post("/uploads/inspect", json={"key": key, "filename": "book.xlsx"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["layers"]) >= 2
    assert body["fields"] == []


def test_inspect_upload_xlsx_with_layer_name_returns_sheet_fields(client, s3_stub, ...):
    ...
    response = client.post(
        "/uploads/inspect",
        json={"key": key, "filename": "book.xlsx", "layerName": "<premier nom de feuille>"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["layers"] == []
    assert isinstance(body["fields"], list) and len(body["fields"]) > 0
```

(Le nom exact de la première feuille de `TwoSheetsNoneHidden.xlsx` doit
être lu depuis `list_xlsx_sheets(...)` en tête du test, pas deviné —
`wb.sheetnames[0]` du fixture réel, déterminé en Task 1 Step 2.)

- [ ] **Step 7 : lancer les tests, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_routes.py -k xlsx -v
```

Attendu : échec — `inspect_upload` renvoie encore `fields` (pas `layers`)
pour tout `.xlsx`, quel que soit le nombre de feuilles.

- [ ] **Step 8 : réécrire la branche `.xlsx` de `inspect_upload`**

Dans `core/app/ingestion/routes.py`, remplacer (L90-95 avant cette tâche) :

```python
    if body.filename.lower().endswith(".xlsx"):
        try:
            fields = read_xlsx_header_fields(content)
        except IngestionParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return InspectResponse(layers=[], fields=fields)
```

par :

```python
    if body.filename.lower().endswith(".xlsx"):
        try:
            if body.layerName is not None:
                fields = read_xlsx_header_fields(content, sheet_name=body.layerName)
                return InspectResponse(layers=[], fields=fields)
            sheets = list_xlsx_sheets(content)
            if len(sheets) > 1:
                return InspectResponse(
                    layers=[
                        LayerInfoOut(
                            name=s.name, featureCount=s.feature_count, geometryType=s.geometry_type
                        )
                        for s in sheets
                    ]
                )
            fields = read_xlsx_header_fields(content)
        except IngestionParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return InspectResponse(layers=[], fields=fields)
```

Ajouter `list_xlsx_sheets` à l'import de `app.ingestion.parsers` en tête de
`routes.py` (déjà importe `IngestionParseError, list_layers,
read_xlsx_header_fields` — ajouter `list_xlsx_sheets` à cette liste).

- [ ] **Step 9 : lancer les tests, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_routes.py -k xlsx -v
```

Attendu : tous passed.

- [ ] **Step 10 : commit**

```bash
git add core/app/ingestion/parsers.py core/app/ingestion/schemas.py \
  core/app/ingestion/routes.py core/tests/test_ingestion_parsers.py \
  core/tests/test_ingestion_routes.py
git commit -m "feat(core): Excel multi-feuilles — list_xlsx_sheets + inspection scopée à une feuille (GAP-29)"
```

---

## Task 6 : généraliser le renommage de propriété réservée

**Files:**
- Modify: `core/app/ingestion/parsers.py:336-343` (`_KML_RESERVED_PROPERTY_NAMES`,
  `_rename_kml_reserved_properties`, usage dans `parse_kml`)
- Modify: `core/tests/test_ingestion_parsers.py` (aucune modification de
  `test_parse_kml_renames_reserved_id_property` — ce test doit rester
  vert **sans y toucher**, c'est la preuve de non-régression)

**Interfaces:**
- Produces: `_rename_reserved_property_keys(props: dict, prefix: str) ->
  dict`. Consommé par Task 7 (GML, préfixe `"gml"`), Task 8 (JSON Lines,
  préfixe `"jsonl"`), Task 10 (XML générique, préfixe `"xml"`).

- [ ] **Step 1 : confirmer l'état rouge/vert AVANT toute modification**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k kml_renames -v
```

Attendu : déjà **passed** (test SP-56 existant, comportement actuel). Ce
n'est pas un test à écrire — c'est le filet de non-régression du refactor
de cette tâche : il doit rester vert de bout en bout, jamais modifié.

- [ ] **Step 2 : ajouter un test caractéristique du nouveau helper générique**

```python
def test_rename_reserved_property_keys_applies_given_prefix():
    from app.ingestion.parsers import _rename_reserved_property_keys

    result = _rename_reserved_property_keys(
        {"id": "1", "tenant_id": "x", "geom": "y", "name": "ok"}, "jsonl"
    )
    assert result == {"jsonl_id": "1", "jsonl_tenant_id": "x", "jsonl_geom": "y", "name": "ok"}
```

- [ ] **Step 3 : lancer, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k rename_reserved -v
```

Attendu : `ImportError: cannot import name '_rename_reserved_property_keys'`.

- [ ] **Step 4 : généraliser**

Remplacer (L336-343 avant cette tâche) :

```python
_KML_RESERVED_PROPERTY_NAMES = {"id", "tenant_id", "geom"}


def _rename_kml_reserved_properties(props: dict) -> dict:
    return {
        (f"kml_{key}" if key in _KML_RESERVED_PROPERTY_NAMES else key): value
        for key, value in props.items()
    }
```

par :

```python
_RESERVED_PROPERTY_NAMES = {"id", "tenant_id", "geom"}


def _rename_reserved_property_keys(props: dict, prefix: str) -> dict:
    """Toute source de données peut légitimement porter une colonne nommée
    id/tenant_id/geom, en collision avec les colonnes fixes que run_import
    pose sur chaque table (id serial PRIMARY KEY, tenant_id, geom) — pour
    KML, cette collision est garantie à 100% (le driver GDAL impose un
    champ id sur tout Placemark, SP-56). Fonction générique, préfixe fourni
    par l'appelant : parse_kml (préfixe "kml", inchangé), parse_gml
    ("gml"), parse_jsonlines ("jsonl"), parse_xml_generic ("xml")."""
    return {
        (f"{prefix}_{key}" if key in _RESERVED_PROPERTY_NAMES else key): value
        for key, value in props.items()
    }
```

Dans `parse_kml` (appel actuel `_rename_kml_reserved_properties(props)`,
dans la boucle `for geom, props in _read_features(path, layer_name): yield
geom, _rename_kml_reserved_properties(props)`), remplacer l'appel par
`_rename_reserved_property_keys(props, "kml")`.

- [ ] **Step 5 : lancer TOUS les tests KML + le nouveau test, vérifier le
  succès**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "kml or rename_reserved" -v
```

Attendu : tous passed, y compris `test_parse_kml_renames_reserved_id_property`
**inchangé** (preuve que le refactor n'a rien changé pour KML).

- [ ] **Step 6 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py
git commit -m "refactor(core): généralise le renommage de propriété réservée KML par préfixe (GAP-29)"
```

---

## Task 7 : format GML

**Files:**
- Modify: `core/app/ingestion/parsers.py` (ajouter `parse_gml` après
  `parse_kml`/`_looks_like_zip` ; étendre `_ALLOWED_TEMP_SUFFIXES`
  (`parsers.py:213`) ; étendre `list_layers` (`parsers.py:390-432`))
- Modify: `core/app/ingestion/schemas.py` (aucun changement dans cette
  tâche — pas de nouveau champ requis pour GML)
- Test: `core/tests/test_ingestion_parsers.py`

**Interfaces:**
- Consumes: `_read_features` (déjà existante), `_rename_reserved_property_keys`
  (Task 6), `_temp_file` (déjà existante), fixture
  `core/tests/fixtures/ingestion/archsites.gml` (Task 1).
- Produces: `parse_gml(content: bytes, layer_name: str | None = None) ->
  Iterator[tuple[BaseGeometry, dict]]`. Consommé par Task 11 (dispatch
  `run_import`).

- [ ] **Step 1 : écrire les tests (fixture réelle)**

```python
def test_parse_gml_yields_geometry_and_properties_reprojected():
    content = (_FIXTURES / "archsites.gml").read_bytes()
    rows = list(parse_gml(content))
    assert len(rows) > 0
    geom, props = rows[0]
    # archsites.gml est en EPSG:26713 (non-WGS84) — vérifier que la
    # reprojection de _read_features s'est bien appliquée : les
    # coordonnées ne doivent plus être de l'ordre de 10^5-10^6 (UTM-like)
    # mais de l'ordre de longitudes/latitudes WGS84 plausibles pour
    # l'Ouest américain (le jeu de données archsites est du Colorado).
    assert -110 < geom.x < -100
    assert 35 < geom.y < 45
    # Les propriétés du fixture réel (§5 de la spec) : à vérifier au nom
    # local exact renvoyé par pyogrio (peut être "cat"/"str1" sans le
    # préfixe de namespace "og:" — à confirmer empiriquement ici).
    assert "cat" in props or "og:cat" in props


def test_list_layers_gml_single_layer():
    content = (_FIXTURES / "archsites.gml").read_bytes()
    layers = list_layers(content, "archsites.gml")
    assert len(layers) == 1
    assert layers[0].geometry_type == "Point"


def test_parse_gml_reserved_property_collision_check():
    """Vérifie empiriquement (piège CLAUDE.md n°3) si le driver GML de GDAL
    impose, comme KML, un champ 'id' — si oui, il doit être renommé
    'gml_id' (comme kml_id pour KML) plutôt que provoquer une collision
    SQL en aval (run_import, Task 11)."""
    content = (_FIXTURES / "archsites.gml").read_bytes()
    _geom, props = next(iter(parse_gml(content)))
    assert "id" not in props  # soit jamais présent, soit déjà renommé gml_id
```

- [ ] **Step 2 : lancer les tests, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "parse_gml or list_layers_gml" -v
```

Attendu : `ImportError: cannot import name 'parse_gml'` (fonction
inexistante) ; `test_list_layers_gml_single_layer` échoue avec `ValueError:
format non concerné par l'inspection : archsites.gml` (branche `.gml`
absente de `list_layers`).

- [ ] **Step 3 : implémenter `parse_gml`**

Ajouter après `_looks_like_zip` (avant `parse_geoparquet`, L363-364 avant
cette tâche) dans `core/app/ingestion/parsers.py` :

```python
def parse_gml(
    content: bytes,
    layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    """GML/INSPIRE traité exactement comme KML (GAP-29, §2.6 de la spec) :
    réutilisation brute de _read_features, aucune logique spécifique au
    schéma INSPIRE. Pas de variante zip (contrairement à KML/KMZ) — un seul
    suffixe possible."""
    with _temp_file(content, ".gml") as path:
        for geom, props in _read_features(path, layer_name):
            yield geom, _rename_reserved_property_keys(props, "gml")
```

Étendre `_ALLOWED_TEMP_SUFFIXES` (L213) :

```python
_ALLOWED_TEMP_SUFFIXES = frozenset({".gpkg", ".zip", ".kml", ".kmz", ".parquet", ".gml"})
```

Étendre `list_layers` (branche `elif lower.endswith((".kml", ".kmz")):` —
L396-408 avant cette tâche) pour inclure `.gml` :

```python
    elif lower.endswith((".kml", ".kmz", ".gml")):
        # Identité : PAS le wrap /vsizip/ de la branche .zip ci-dessus.
        if lower.endswith(".kmz"):
            suffix = ".kmz"
        elif lower.endswith(".gml"):
            suffix = ".gml"
        else:
            suffix = ".kml"
        wrap = lambda p: p  # noqa: E731 — cohérent avec la forme déjà en vigueur ici
```

(Reprendre la structure `if/elif` déjà présente et l'étendre — lire le code
réel de `list_layers` avant d'éditer, la forme exacte du bloc peut différer
légèrement du extrait ci-dessus selon l'état du fichier après les tâches
précédentes.)

- [ ] **Step 4 : lancer les tests, vérifier le succès (ou ajuster selon le
  résultat empirique)**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "parse_gml or list_layers_gml" -v
```

Attendu : `test_parse_gml_yields_geometry_and_properties_reprojected` et
`test_list_layers_gml_single_layer` passent. Pour
`test_parse_gml_reserved_property_collision_check` : lire le résultat réel
de `props` affiché par un `print()` temporaire ou `pytest -v --tb=long`
avant de décider — si `id` est bien absent nativement (pas besoin du
renommage), le test passe déjà sans changement supplémentaire ; si `id` est
présent malgré le renommage attendu, cela signifie que
`_rename_reserved_property_keys` n'est pas appelée correctement (bug à
corriger, pas une simple constatation) — ne jamais ajuster silencieusement
l'assertion pour la faire passer sans comprendre pourquoi.

- [ ] **Step 5 : documenter le résultat empirique dans un commentaire**

Ajouter, au-dessus de `parse_gml`, une ligne factuelle sur ce qui a été
observé (ex. « Vérifié empiriquement : le driver GML de GDAL n'expose pas
de champ 'id' automatique comme KML — le renommage réservé ci-dessous est
appliqué par défense en profondeur, sans effet sur ce fixture. » ou
l'inverse selon le résultat réel).

- [ ] **Step 6 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py
git commit -m "feat(core): ajoute le parseur GML/INSPIRE, réutilise _read_features (GAP-29)"
```

---

## Task 8 : format JSON Lines

**Files:**
- Modify: `core/app/ingestion/parsers.py` (ajouter `parse_jsonlines`,
  `read_jsonlines_header_fields`)
- Modify: `core/app/ingestion/routes.py` (`inspect_upload`, branche `.jsonl`)
- Test: `core/tests/test_ingestion_parsers.py`, `core/tests/test_ingestion_routes.py`

**Interfaces:**
- Consumes: `GeometryMode`, `extract_geometry` (Task 2),
  `_rename_reserved_property_keys` (Task 6), fixture
  `scifact_claims_sample.jsonl` (Task 1).
- Produces: `parse_jsonlines(content: bytes, mode: GeometryMode) ->
  Iterator[tuple[BaseGeometry | None, dict]]`,
  `read_jsonlines_header_fields(content: bytes, sample_lines: int = 20) ->
  list[str]`. Consommé par Task 11.

- [ ] **Step 1 : écrire les tests**

```python
def test_parse_jsonlines_scalar_and_nested_values():
    content = (_FIXTURES / "scifact_claims_sample.jsonl").read_bytes()
    rows = list(parse_jsonlines(content, GeometryMode(kind="none")))
    assert len(rows) == 10
    geom, props = rows[0]
    assert geom is None
    # collision réservée : la clé "id" du fixture doit être renommée
    assert "id" not in props
    assert "jsonl_id" in props
    # valeur imbriquée (dict/list) sérialisée en JSON compact, pas un objet Python
    assert isinstance(props["evidence"], str)
    json.loads(props["evidence"])  # doit rester du JSON valide


def test_parse_jsonlines_rejects_malformed_line():
    content = b'{"a": 1}\nnot json\n'
    with pytest.raises(IngestionParseError, match="ligne 2"):
        list(parse_jsonlines(content, GeometryMode(kind="none")))


def test_parse_jsonlines_rejects_non_object_line():
    content = b'{"a": 1}\n[1, 2, 3]\n'
    with pytest.raises(IngestionParseError, match="objet JSON"):
        list(parse_jsonlines(content, GeometryMode(kind="none")))


def test_parse_jsonlines_latlon_mode():
    content = b'{"lat": 48.85, "lon": 2.35, "name": "Paris"}\n'
    rows = list(
        parse_jsonlines(content, GeometryMode(kind="latlon", lat_field="lat", lon_field="lon"))
    )
    assert rows[0][0].equals(Point(2.35, 48.85))


def test_read_jsonlines_header_fields_samples_first_lines():
    content = (_FIXTURES / "scifact_claims_sample.jsonl").read_bytes()
    fields = read_jsonlines_header_fields(content, sample_lines=3)
    assert "id" in fields and "claim" in fields
```

- [ ] **Step 2 : lancer, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k jsonlines -v
```

Attendu : `ImportError: cannot import name 'parse_jsonlines'`.

- [ ] **Step 3 : implémenter**

Ajouter dans `core/app/ingestion/parsers.py` (après `parse_gml`, Task 7) :

```python
def parse_jsonlines(
    content: bytes,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    for i, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestionParseError(f"ligne {i} : JSON invalide ({exc})") from exc
        if not isinstance(row, dict):
            raise IngestionParseError(f"ligne {i} : chaque ligne doit être un objet JSON")
        row = {
            k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in row.items()
        }
        row = _rename_reserved_property_keys(row, "jsonl")
        try:
            yield extract_geometry(row, mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc


def read_jsonlines_header_fields(content: bytes, sample_lines: int = 20) -> list[str]:
    """Union des clés des N premières lignes non vides — jamais tout le
    fichier (utilisé par POST /uploads/inspect uniquement ; le job d'import
    réel, parse_jsonlines, traite lui la totalité des lignes)."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    fields: dict[str, None] = {}
    seen = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestionParseError(f"JSON invalide dans l'échantillon : {exc}") from exc
        if isinstance(row, dict):
            for key in row:
                fields.setdefault(key, None)
        seen += 1
        if seen >= sample_lines:
            break
    return list(fields.keys())
```

- [ ] **Step 4 : lancer, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k jsonlines -v
```

Attendu : tous passed.

- [ ] **Step 5 : ajouter la branche `.jsonl` à `inspect_upload`**

Écrire d'abord le test (`core/tests/test_ingestion_routes.py`) :

```python
def test_inspect_upload_jsonlines_returns_fields(client, s3_stub, ...):
    ...
    response = client.post("/uploads/inspect", json={"key": key, "filename": "data.jsonl"})
    assert response.status_code == 200
    body = response.json()
    assert body["layers"] == []
    assert "id" in body["fields"] or "jsonl_id" in body["fields"]
```

Lancer, vérifier l'échec (`inspect_upload` ne reconnaît pas `.jsonl`, tombe
dans la branche `list_layers` générique → `ValueError`/400). Puis, dans
`core/app/ingestion/routes.py::inspect_upload`, ajouter la branche avant le
`try: layers = list_layers(...)` final :

```python
    if body.filename.lower().endswith(".jsonl"):
        try:
            fields = read_jsonlines_header_fields(content)
        except IngestionParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return InspectResponse(layers=[], fields=fields)
```

Ajouter `read_jsonlines_header_fields` à l'import `app.ingestion.parsers`
en tête de `routes.py`. Relancer le test — passed.

- [ ] **Step 6 : commit**

```bash
git add core/app/ingestion/parsers.py core/app/ingestion/routes.py \
  core/tests/test_ingestion_parsers.py core/tests/test_ingestion_routes.py
git commit -m "feat(core): ajoute le parseur JSON Lines (GAP-29)"
```

---

## Task 9 : format Parquet non-géo

**Files:**
- Modify: `core/app/ingestion/parsers.py` (ajouter `_is_geoparquet`,
  `parse_parquet_tabular`, `read_parquet_header_fields`)
- Modify: `core/app/ingestion/routes.py` (`inspect_upload`, branche
  `.parquet` distinguant geo/non-géo)
- Test: `core/tests/test_ingestion_parsers.py`, `core/tests/test_ingestion_routes.py`

**Interfaces:**
- Consumes: `GeometryMode`, `extract_geometry` (Task 2), `_temp_file`
  (existante).
- Produces: `_is_geoparquet(path: str) -> bool`,
  `_is_geoparquet_from_bytes(content: bytes) -> bool`,
  `parse_parquet_tabular(content: bytes, mode: GeometryMode) ->
  Iterator[tuple[BaseGeometry | None, dict]]`,
  `read_parquet_header_fields(content: bytes) -> list[str]`. Consommé par
  Task 11 (dispatch `.parquet` dans `run_import`, via `_is_geoparquet`) et
  la branche `.parquet` d'`inspect_upload` dans cette même tâche (via
  `_is_geoparquet_from_bytes`).

- [ ] **Step 1 : écrire les tests (fixtures synthétiques, cf. spec §5 — pas
  de fixture réelle requise pour ce format)**

```python
import pyarrow as pa
import pyarrow.parquet as pq


def _write_tabular_parquet(path, rows: list[dict]):
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)  # aucune métadonnée "geo" — non-géo par construction


def test_is_geoparquet_false_for_plain_parquet(tmp_path):
    path = tmp_path / "plain.parquet"
    _write_tabular_parquet(path, [{"name": "A", "value": 1}])
    assert _is_geoparquet(str(path)) is False


def test_is_geoparquet_true_for_existing_geoparquet_fixture(tmp_path):
    # Réutilise le patron de test_parse_geoparquet_yields_geometry_and_attributes
    # (SP-56, même fichier) pour écrire un vrai GeoParquet avec la clé "geo".
    import geopandas as gpd
    from shapely.geometry import Point as ShapelyPoint

    gdf = gpd.GeoDataFrame({"name": ["A"]}, geometry=[ShapelyPoint(1, 2)], crs="EPSG:4326")
    path = tmp_path / "geo.parquet"
    gdf.to_parquet(path)
    assert _is_geoparquet(str(path)) is True


def test_parse_parquet_tabular_none_mode(tmp_path):
    path = tmp_path / "plain.parquet"
    _write_tabular_parquet(path, [{"name": "A", "value": 1}, {"name": "B", "value": 2}])
    rows = list(parse_parquet_tabular(path.read_bytes(), GeometryMode(kind="none")))
    assert len(rows) == 2
    assert rows[0][0] is None
    assert rows[0][1] == {"name": "A", "value": 1}


def test_parse_parquet_tabular_serializes_nested_struct(tmp_path):
    path = tmp_path / "nested.parquet"
    _write_tabular_parquet(path, [{"name": "A", "tags": ["x", "y"]}])
    rows = list(parse_parquet_tabular(path.read_bytes(), GeometryMode(kind="none")))
    assert isinstance(rows[0][1]["tags"], str)
    assert json.loads(rows[0][1]["tags"]) == ["x", "y"]


def test_read_parquet_header_fields(tmp_path):
    path = tmp_path / "plain.parquet"
    _write_tabular_parquet(path, [{"name": "A", "value": 1}])
    fields = read_parquet_header_fields(path.read_bytes())
    assert set(fields) == {"name", "value"}
```

- [ ] **Step 2 : lancer, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "geoparquet_false or geoparquet_true or parquet_tabular or parquet_header" -v
```

Attendu : `ImportError`/`NameError` sur les fonctions inexistantes.

- [ ] **Step 3 : implémenter**

Ajouter dans `core/app/ingestion/parsers.py` (après `parse_geoparquet`,
avant `list_layers`) :

```python
import pyarrow.parquet


def _is_geoparquet(path: str) -> bool:
    """Sniffe la clé "geo" des métadonnées Parquet (spec GeoParquet 1.0) —
    lit le footer via read_schema, jamais les données."""
    schema = pyarrow.parquet.read_schema(path)
    return b"geo" in (schema.metadata or {})


def parse_parquet_tabular(
    content: bytes,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    with _temp_file(content, ".parquet") as path:
        table = pyarrow.parquet.read_table(path)
        for row in table.to_pylist():
            row = {
                k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in row.items()
            }
            yield extract_geometry(row, mode)


def read_parquet_header_fields(content: bytes) -> list[str]:
    with _temp_file(content, ".parquet") as path:
        schema = pyarrow.parquet.read_schema(path)
        return list(schema.names)
```

(`import pyarrow.parquet` : ajouter en tête du fichier avec les autres
imports tiers, à côté de `import geopandas as gpd`.)

- [ ] **Step 4 : lancer, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "geoparquet_false or geoparquet_true or parquet_tabular or parquet_header" -v
```

Attendu : tous passed.

- [ ] **Step 5 : ajouter la branche `.parquet` à `inspect_upload`**

Écrire le test :

```python
def test_inspect_upload_geoparquet_returns_null_fields_sentinel(client, s3_stub, ...):
    # upload d'un GeoParquet réel (cf. patron test_parse_geoparquet existant)
    ...
    response = client.post("/uploads/inspect", json={"key": key, "filename": "data.parquet"})
    assert response.status_code == 200
    assert response.json()["fields"] is None


def test_inspect_upload_tabular_parquet_returns_field_list(client, s3_stub, ...):
    ...
    response = client.post("/uploads/inspect", json={"key": key, "filename": "data.parquet"})
    assert response.status_code == 200
    assert isinstance(response.json()["fields"], list)
```

Lancer, vérifier l'échec (`inspect_upload` ne reconnaît pas `.parquet` du
tout aujourd'hui — tombe dans `list_layers` générique → erreur).

**Signature manquante à ajouter d'abord** : `_is_geoparquet(path: str)`
(Step 3) prend un chemin de fichier, pas des `bytes` — `routes.py` ne doit
pas dupliquer `_temp_file` lui-même pour en obtenir un. Ajouter dans
`core/app/ingestion/parsers.py`, juste après `_is_geoparquet` :

```python
def _is_geoparquet_from_bytes(content: bytes) -> bool:
    """Variante bytes de _is_geoparquet, pour les appelants (routes.py) qui
    n'ont pas déjà de fichier temporaire ouvert — run_import (Task 11), qui
    lui en ouvre un pour lire les données ensuite, appelle _is_geoparquet(path)
    directement plutôt que de rouvrir un second fichier temporaire."""
    with _temp_file(content, ".parquet") as path:
        return _is_geoparquet(path)
```

Ajouter le test correspondant, à côté de `test_is_geoparquet_true_for_existing_geoparquet_fixture` :

```python
def test_is_geoparquet_from_bytes_true_for_existing_geoparquet_fixture(tmp_path):
    import geopandas as gpd
    from shapely.geometry import Point as ShapelyPoint

    gdf = gpd.GeoDataFrame({"name": ["A"]}, geometry=[ShapelyPoint(1, 2)], crs="EPSG:4326")
    path = tmp_path / "geo.parquet"
    gdf.to_parquet(path)
    assert _is_geoparquet_from_bytes(path.read_bytes()) is True
```

Lancer `cd core && uv run pytest tests/test_ingestion_parsers.py -k
is_geoparquet_from_bytes -v`, vérifier le succès, puis ajouter la branche
dans `core/app/ingestion/routes.py::inspect_upload` :

```python
    if body.filename.lower().endswith(".parquet"):
        if _is_geoparquet_from_bytes(content):
            return InspectResponse(layers=[], fields=None)
        try:
            fields = read_parquet_header_fields(content)
        except IngestionParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return InspectResponse(layers=[], fields=fields)
```

Ajouter `_is_geoparquet_from_bytes`, `read_parquet_header_fields` à l'import
`app.ingestion.parsers` en tête de `routes.py`.

- [ ] **Step 6 : lancer, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_routes.py -k parquet -v
```

Attendu : tous passed.

- [ ] **Step 7 : commit**

```bash
git add core/app/ingestion/parsers.py core/app/ingestion/routes.py \
  core/tests/test_ingestion_parsers.py core/tests/test_ingestion_routes.py
git commit -m "feat(core): ajoute le parseur Parquet non-géo, sniff de la clé geo (GAP-29)"
```

---

## Task 10 : format XML générique

**Files:**
- Modify: `core/app/ingestion/parsers.py` (ajouter `_find_repeated_element`,
  `_local_name`, `parse_xml_generic`, `read_xml_header_fields`)
- Modify: `core/app/ingestion/routes.py` (`inspect_upload`, branche `.xml`)
- Test: `core/tests/test_ingestion_parsers.py`, `core/tests/test_ingestion_routes.py`

**Interfaces:**
- Consumes: `GeometryMode`, `extract_geometry` (Task 2),
  `_rename_reserved_property_keys` (Task 6), fixture `books.xml` (Task 1),
  `defusedxml` (dépendance déjà présente).
- Produces: `parse_xml_generic(content: bytes, mode: GeometryMode) ->
  Iterator[tuple[BaseGeometry | None, dict]]`, `read_xml_header_fields(
  content: bytes) -> list[str]`. Consommé par Task 11.

- [ ] **Step 1 : écrire les tests**

```python
def test_parse_xml_generic_detects_repeated_book_element():
    content = (_FIXTURES / "books.xml").read_bytes()
    rows = list(parse_xml_generic(content, GeometryMode(kind="none")))
    assert len(rows) > 1
    geom, props = rows[0]
    assert geom is None
    assert props["author"] == "Gambardella, Matthew"
    assert props["title"] == "XML Developer's Guide"
    # collision réservée : l'attribut id="bk101" doit être renommé xml_id
    assert "id" not in props
    assert props["xml_id"] == "bk101"
    # enfant texte multi-lignes : doit être strippé, pas laissé avec
    # l'indentation XML brute
    assert not props["description"].startswith("\n")


def test_parse_xml_generic_no_repeated_element_fails_fast():
    content = b"<root><a>1</a><b>2</b></root>"
    with pytest.raises(IngestionParseError, match="aucun élément répété"):
        list(parse_xml_generic(content, GeometryMode(kind="none")))


def test_parse_xml_generic_ignores_structured_children():
    content = b"""<catalog>
      <item><name>A</name><nested><x>1</x></nested></item>
      <item><name>B</name><nested><x>2</x></nested></item>
    </catalog>"""
    rows = list(parse_xml_generic(content, GeometryMode(kind="none")))
    assert len(rows) == 2
    assert "nested" not in rows[0][1]
    assert rows[0][1]["name"] == "A"


def test_local_name_strips_namespace_uri():
    content = b"""<ns:catalog xmlns:ns="http://example.org">
      <ns:item><ns:name>A</ns:name></ns:item>
      <ns:item><ns:name>B</ns:name></ns:item>
    </ns:catalog>"""
    rows = list(parse_xml_generic(content, GeometryMode(kind="none")))
    assert rows[0][1] == {"name": "A"}


def test_parse_xml_generic_latlon_mode():
    content = b"""<rows>
      <row><lat>48.85</lat><lon>2.35</lon></row>
      <row><lat>45.75</lat><lon>4.85</lon></row>
    </rows>"""
    rows = list(
        parse_xml_generic(content, GeometryMode(kind="latlon", lat_field="lat", lon_field="lon"))
    )
    assert rows[0][0].equals(Point(2.35, 48.85))


def test_read_xml_header_fields():
    content = (_FIXTURES / "books.xml").read_bytes()
    fields = read_xml_header_fields(content)
    assert "author" in fields and "title" in fields and "xml_id" in fields
```

- [ ] **Step 2 : lancer, vérifier l'échec**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "xml_generic or local_name" -v
```

Attendu : `ImportError`/`NameError` — aucune de ces fonctions n'existe.

- [ ] **Step 3 : implémenter l'algorithme de détection + le parseur**

Ajouter dans `core/app/ingestion/parsers.py` (après `read_parquet_header_fields`,
Task 9) :

```python
import defusedxml.ElementTree


def _local_name(tag: str) -> str:
    """Retire un préfixe d'espace de noms ('{uri}local' -> 'local') —
    ElementTree qualifie les tags par l'URI complète dès qu'un xmlns est
    déclaré."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_repeated_element(root):
    """BFS (ordre du document) — le premier parent dont un même nom
    d'enfant apparaît >= 2 fois gagne. Retourne (parent, tag_repete) ou
    (None, None) si aucun ne qualifie."""
    from collections import Counter, deque

    queue = deque([root])
    while queue:
        parent = queue.popleft()
        counts = Counter(_local_name(child.tag) for child in parent)
        repeated = next((tag for tag, n in counts.items() if n >= 2), None)
        if repeated is not None:
            return parent, repeated
        queue.extend(parent)
    return None, None


def parse_xml_generic(
    content: bytes,
    mode: GeometryMode,
) -> Iterator[tuple[BaseGeometry | None, dict]]:
    try:
        root = defusedxml.ElementTree.fromstring(content)
    except defusedxml.ElementTree.ParseError as exc:
        raise IngestionParseError(f"XML invalide : {exc}") from exc
    parent, tag = _find_repeated_element(root)
    if parent is None:
        raise IngestionParseError("aucun élément répété détecté — format non reconnu")
    matching = [e for e in parent if _local_name(e.tag) == tag]
    for i, elem in enumerate(matching, start=1):
        row: dict = dict(elem.attrib)
        for child in elem:
            if len(child) == 0:  # feuille texte, pas un sous-élément structuré
                row[_local_name(child.tag)] = (child.text or "").strip()
        row = _rename_reserved_property_keys(row, "xml")
        try:
            yield extract_geometry(row, mode)
        except IngestionParseError as exc:
            raise IngestionParseError(f"ligne {i} : {exc}") from exc


def read_xml_header_fields(content: bytes) -> list[str]:
    fields: dict[str, None] = {}
    for _geom, props in parse_xml_generic(content, GeometryMode(kind="none")):
        for key in props:
            fields.setdefault(key, None)
    return list(fields.keys())
```

`defusedxml.ElementTree.ParseError` — vérifier le nom exact de l'exception
levée par cette version verrouillée de `defusedxml` (piège CLAUDE.md n°3,
signatures de bibliothèque tierce à vérifier contre la source réelle, pas
supposées) :

```bash
cd core && uv run python3 -c "
import defusedxml.ElementTree as ET
try:
    ET.fromstring(b'<not valid xml')
except Exception as e:
    print(type(e).__module__, type(e).__name__)
"
```

Ajuster le `except` de `parse_xml_generic` avec le nom réel affiché si
différent de `defusedxml.ElementTree.ParseError`.

- [ ] **Step 4 : lancer, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_parsers.py -k "xml_generic or local_name or read_xml_header" -v
```

Attendu : tous passed.

- [ ] **Step 5 : ajouter la branche `.xml` à `inspect_upload`**

Écrire le test :

```python
def test_inspect_upload_xml_generic_returns_fields(client, s3_stub, ...):
    ...
    response = client.post("/uploads/inspect", json={"key": key, "filename": "catalog.xml"})
    assert response.status_code == 200
    body = response.json()
    assert body["layers"] == []
    assert "author" in body["fields"]
```

Lancer, vérifier l'échec. Puis dans `routes.py::inspect_upload`, ajouter :

```python
    if body.filename.lower().endswith(".xml"):
        try:
            fields = read_xml_header_fields(content)
        except IngestionParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return InspectResponse(layers=[], fields=fields)
```

**Ordre des branches important** : cette branche doit être testée
**avant** la branche `list_layers` générique (qui rejette aujourd'hui
`.xml` avec `ValueError`) mais peut être placée n'importe où relativement
aux branches `.xlsx`/`.jsonl`/`.parquet` (extensions mutuellement
exclusives, aucun chevauchement). Ajouter `read_xml_header_fields` à
l'import `app.ingestion.parsers` de `routes.py`.

- [ ] **Step 6 : lancer, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_routes.py -k xml -v
```

Attendu : tous passed.

- [ ] **Step 7 : commit**

```bash
git add core/app/ingestion/parsers.py core/app/ingestion/routes.py \
  core/tests/test_ingestion_parsers.py core/tests/test_ingestion_routes.py
git commit -m "feat(core): ajoute le parseur XML générique (élément répété, GAP-29)"
```

---

## Task 11 : intégration `run_import` — dispatch complet, table sans géométrie

**Files:**
- Modify: `core/app/ingestion/schemas.py:15-21` (`IngestionJobCreate` gagne
  `wktField`/`geometryMode`)
- Modify: `core/app/ingestion/importer.py` (imports L23-32, `_pick_format`
  L55-71, `ImportResult` L49-52, `run_import` L92-254 : dispatch, table
  sans géométrie, pas de Map créée)
- Modify: `core/app/ingestion/routes.py` (`create_upload_job`, relayer les
  2 nouveaux champs de `IngestionJobCreate` vers `repo.create_job` — vérifier
  d'abord si `repo.create_job`/le modèle `IngestionJob` a besoin d'être
  étendu pour persister ces champs jusqu'au moment où le job tourne)
- Modify: `core/app/ingestion/repository.py` (`create_job` gagne
  `wkt_field`/`geometry_mode`, même patron que `lat_field`/`lon_field`/
  `layer_name` déjà présents)
- Modify: `core/app/ingestion/models.py` (`IngestionJob` gagne les 2
  colonnes ; migration Alembic)
- Modify: `core/app/ingestion/tasks.py:84-107`
  (`run_ingestion_task` déstructure et relaie les 2 nouveaux champs du job
  vers `run_import`)
- Test: `core/tests/test_ingestion_importer.py`, `core/tests/test_ingestion_routes.py`

**Interfaces:**
- Consumes: `parse_gml` (Task 7), `parse_jsonlines` (Task 8),
  `parse_parquet_tabular`/`_is_geoparquet` (Task 9), `parse_xml_generic`
  (Task 10), `parse_csv_latlon`/`parse_xlsx_sheet` (Tasks 3-4), tous en
  forme `GeometryMode`.
- Produces: `ImportResult.item_id: str | None` (changé — Task 12 en dépend
  côté shell), `_resolve_geometry_mode(lat_field, lon_field, wkt_field,
  geometry_mode) -> GeometryMode`, `run_import(..., wkt_field: str | None =
  None, geometry_mode: str | None = None)` (2 nouveaux kwargs).

**Vérifié avant d'écrire cette tâche (pas supposé)** : `run_import`
(`core/app/ingestion/importer.py:92-103`) prend des kwargs individuels —
`tenant_id`, `created_by`, `filename`, `content`, `collection_title`,
`lat_field`, `lon_field`, `layer_name=None` — **pas** un objet `job`.
`run_ingestion_task` (`core/app/ingestion/tasks.py:84-107`) lit la ligne
`IngestionJob` une fois (`job.filename`, `job.source_key`, `job.lat_field`,
`job.lon_field`, `job.layer_name`, `job.created_by`, `job.collection_title`
— tuple de déstructuration L84-92), puis appelle `run_import(...)` avec ces
valeurs individuelles (L97-107). Les deux nouveaux champs suivent donc
exactement ce patron : colonnes sur `IngestionJob`, kwargs individuels sur
`run_import`, pas un objet passé tel quel.

- [ ] **Step 1 : migration Alembic**

```bash
cd core && uv run alembic revision -m "add wkt_field and geometry_mode to ingestion_jobs"
```

Éditer le fichier généré sous `core/alembic/versions/` :

```python
def upgrade() -> None:
    op.add_column("ingestion_jobs", sa.Column("wkt_field", sa.String(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("geometry_mode", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "geometry_mode")
    op.drop_column("ingestion_jobs", "wkt_field")
```

Ajouter les deux colonnes correspondantes au modèle SQLAlchemy
`IngestionJob` (`core/app/ingestion/models.py`), suivant exactement le
patron déjà en vigueur pour `lat_field`/`lon_field`/`layer_name` sur ce
même modèle (nullable, même style de `Mapped[str | None]`). **Piège
CLAUDE.md déjà documenté** : le conteneur `postgis-test` local n'est pas
tracké par Alembic — un `ALTER TABLE` manuel peut être nécessaire après
cette migration pour que la suite de tests locale ne cascade pas en
`UndefinedColumn` sans rapport avec ce plan.

- [ ] **Step 2 : `IngestionJobCreate` gagne les 2 champs**

Dans `core/app/ingestion/schemas.py`, remplacer :

```python
class IngestionJobCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    collectionTitle: str = Field(min_length=1)
    latField: str | None = None
    lonField: str | None = None
    layerName: str | None = None
```

par :

```python
class IngestionJobCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    collectionTitle: str = Field(min_length=1)
    latField: str | None = None
    lonField: str | None = None
    layerName: str | None = None
    wktField: str | None = None
    geometryMode: Literal["latlon", "wkt", "none"] | None = None
```

(Ajouter `from typing import Literal` en tête de `schemas.py` si absent.)

- [ ] **Step 3 : relayer les 2 champs dans `repo.create_job`/`create_upload_job`**

Dans `core/app/ingestion/repository.py::create_job`, ajouter
`wkt_field: str | None = None`, `geometry_mode: str | None = None` aux
paramètres (à côté de `lat_field`/`lon_field`/`layer_name` déjà présents),
les assigner sur l'instance `IngestionJob` créée. Dans
`routes.py::create_upload_job`, relayer `body.wktField`/`body.geometryMode`
dans l'appel existant à `repo.create_job(...)`.

- [ ] **Step 4 : `_resolve_geometry_mode` + tests unitaires**

Écrire d'abord le test dans `core/tests/test_ingestion_importer.py` :

```python
def test_resolve_geometry_mode_defaults_to_latlon_autodetect():
    mode = _resolve_geometry_mode(
        lat_field=None, lon_field=None, wkt_field=None, geometry_mode=None
    )
    assert mode == GeometryMode(kind="latlon", lat_field=None, lon_field=None)


def test_resolve_geometry_mode_wkt():
    mode = _resolve_geometry_mode(
        lat_field=None, lon_field=None, wkt_field="geom_wkt", geometry_mode="wkt"
    )
    assert mode == GeometryMode(kind="wkt", wkt_field="geom_wkt")


def test_resolve_geometry_mode_none():
    mode = _resolve_geometry_mode(
        lat_field=None, lon_field=None, wkt_field=None, geometry_mode="none"
    )
    assert mode == GeometryMode(kind="none")
```

Lancer, vérifier l'échec (`ImportError`). Implémenter dans
`core/app/ingestion/importer.py` (avant `run_import`) :

```python
def _resolve_geometry_mode(
    *,
    lat_field: str | None,
    lon_field: str | None,
    wkt_field: str | None,
    geometry_mode: str | None,
) -> GeometryMode:
    if geometry_mode == "wkt":
        return GeometryMode(kind="wkt", wkt_field=wkt_field)
    if geometry_mode == "none":
        return GeometryMode(kind="none")
    return GeometryMode(kind="latlon", lat_field=lat_field, lon_field=lon_field)
```

Lancer, vérifier le succès.

- [ ] **Step 5 : étendre `run_import`, `_pick_format` et le dispatch**

Étendre la signature de `run_import` (`core/app/ingestion/importer.py:92-103`) :

```python
def run_import(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    filename: str,
    content: bytes,
    collection_title: str,
    lat_field: str | None,
    lon_field: str | None,
    layer_name: str | None = None,
    wkt_field: str | None = None,
    geometry_mode: str | None = None,
) -> ImportResult:
```

Dans `core/app/ingestion/importer.py`, étendre `_pick_format` (L55-71) :

```python
def _pick_format(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".geojson", ".json")):
        return "geojson"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".gpkg"):
        return "gpkg"
    if lower.endswith(".zip"):
        return "shapefile"
    if lower.endswith((".kml", ".kmz")):
        return "kml"
    if lower.endswith(".gml"):
        return "gml"
    if lower.endswith(".jsonl"):
        return "jsonlines"
    if lower.endswith(".xml"):
        return "xml_generic"
    if lower.endswith(".parquet"):
        return "parquet"  # désambiguïsé par contenu, cf. run_import
    raise IngestionParseError(f"format non supporté : {filename}")
```

Dans `run_import` (corps, L104-120 avant cette tâche), remplacer le bloc de
dispatch :

```python
    mode = _resolve_geometry_mode(
        lat_field=lat_field, lon_field=lon_field, wkt_field=wkt_field, geometry_mode=geometry_mode
    )
    fmt = _pick_format(filename)
    if fmt == "geojson":
        rows = list(parse_geojson(content))
    elif fmt == "csv":
        rows = list(parse_csv_latlon(content, mode))
    elif fmt == "xlsx":
        rows = list(parse_xlsx_sheet(content, layer_name, mode))
    elif fmt == "gpkg":
        rows = list(parse_gpkg(content, layer_name))
    elif fmt == "shapefile":
        rows = list(parse_shapefile_zip(content, layer_name))
    elif fmt == "kml":
        rows = list(parse_kml(content, layer_name))
    elif fmt == "gml":
        rows = list(parse_gml(content, layer_name))
    elif fmt == "jsonlines":
        rows = list(parse_jsonlines(content, mode))
    elif fmt == "xml_generic":
        rows = list(parse_xml_generic(content, mode))
    elif fmt == "parquet":
        with _temp_file(content, ".parquet") as tmp_path:
            is_geo = _is_geoparquet(tmp_path)
        rows = list(parse_geoparquet(content)) if is_geo else list(parse_parquet_tabular(content, mode))
    else:  # pragma: no cover — jamais atteint, _pick_format lève avant
        raise IngestionParseError(f"format non supporté : {filename}")
```

Ajouter à l'import `app.ingestion.parsers` en tête d'`importer.py` :
`GeometryMode`, `_is_geoparquet`, `_temp_file`, `parse_gml`,
`parse_jsonlines`, `parse_parquet_tabular`, `parse_xml_generic`,
`parse_xlsx_sheet` (remplace `parse_xlsx_latlon`).

- [ ] **Step 6 : relayer les 2 nouveaux champs dans `run_ingestion_task`**

Dans `core/app/ingestion/tasks.py`, le tuple de déstructuration existant
(L84-92) :

```python
            filename, source_key, collection_title, lat_field, lon_field, layer_name, created_by = (
                job.filename,
                job.source_key,
                job.collection_title,
                job.lat_field,
                job.lon_field,
                job.layer_name,
                job.created_by,
            )
```

devient :

```python
            (
                filename,
                source_key,
                collection_title,
                lat_field,
                lon_field,
                layer_name,
                wkt_field,
                geometry_mode,
                created_by,
            ) = (
                job.filename,
                job.source_key,
                job.collection_title,
                job.lat_field,
                job.lon_field,
                job.layer_name,
                job.wkt_field,
                job.geometry_mode,
                job.created_by,
            )
```

Et l'appel à `run_import` (L97-107) gagne les 2 kwargs :

```python
            result = run_import(
                session,
                tenant_id=tenant_id,
                created_by=created_by,
                filename=filename,
                content=content,
                collection_title=collection_title,
                lat_field=lat_field,
                lon_field=lon_field,
                layer_name=layer_name,
                wkt_field=wkt_field,
                geometry_mode=geometry_mode,
            )
```

- [ ] **Step 7 : table sans géométrie, pas de Map créée**

Après la construction de `rows` (Step 5), avant la construction des
colonnes (L124-136 avant cette tâche), ajouter :

```python
    has_geometry = any(geom is not None for geom, _props in rows)
```

Modifier la construction de `create_sql` (L142-157 avant cette tâche) :

```python
    create_sql = f"CREATE TABLE public.{t} (id serial PRIMARY KEY, tenant_id text NOT NULL"
    if col_defs:
        create_sql += f", {col_defs}"
    if has_geometry:
        create_sql += f", geom geometry({pg_geom_type}, 4326))"
    else:
        create_sql += ")"
    session.execute(text(create_sql))
```

Modifier l'insertion (L160-176 avant cette tâche) : `insert_cols_full`/
`values_clause`/la boucle de construction de `params` doivent omettre
`geom`/`ST_GeomFromText(:geom_wkt, 4326)` quand `not has_geometry` :

```python
    col_names = list(columns.keys())
    insert_cols = ", ".join(quote_ident(session, name) for name in col_names)
    if has_geometry:
        insert_cols_full = "tenant_id, " + (insert_cols + ", " if insert_cols else "") + "geom"
    else:
        insert_cols_full = "tenant_id" + (", " + insert_cols if insert_cols else "")
    placeholders = ", ".join(f":{name}" for name in col_names)
    if has_geometry:
        values_clause = (
            ":tenant_id, "
            + (placeholders + ", " if placeholders else "")
            + "ST_GeomFromText(:geom_wkt, 4326)"
        )
    else:
        values_clause = ":tenant_id" + (", " + placeholders if placeholders else "")
    insert_sql = f"INSERT INTO public.{t} ({insert_cols_full}) VALUES ({values_clause})"
    params = []
    for geom, props in rows:
        row_params = {name: props.get(name) for name in col_names}
        row_params["tenant_id"] = tenant_id
        if has_geometry:
            row_params["geom_wkt"] = geom.wkt if geom is not None else None
        params.append(row_params)
    session.execute(text(insert_sql), params)
```

(Si `has_geometry` est vrai, chaque `geom` de `rows` est garanti non-`None`
par construction du mode choisi — un seul mode par import, jamais mixte —
donc `geom.wkt` ne lève jamais `AttributeError` sur `None` dans cette
branche ; documenté explicitement dans la spec §2.9.)

Modifier `ImportResult` (L49-52) :

```python
@dataclass
class ImportResult:
    collection_id: str
    item_id: str | None
```

Modifier la fin de `run_import` (L219-254 avant cette tâche) pour sauter la
création de Map/Item/Config quand `not has_geometry` :

```python
    if not has_geometry:
        return ImportResult(collection_id=col.id, item_id=None)

    core_base_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200") + "/v1"
    item = items_repo.create_item(...)  # code existant inchangé, inchangé jusqu'au `return` final
    ...
    return ImportResult(collection_id=col.id, item_id=item.id)
```

- [ ] **Step 8 : tests d'intégration `run_import` par format (au moins un
  par nouveau format + le cas sans géométrie)**

Ajouter à `core/tests/test_ingestion_importer.py` (reprendre le patron des
tests `run_import` existants pour GeoJSON/CSV — session Postgres réelle,
`introspect_table` après import) :

```python
def test_run_import_gml_creates_collection_with_reprojected_geometry(session, ...):
    content = (Path(__file__).parent / "fixtures" / "ingestion" / "archsites.gml").read_bytes()
    result = run_import(
        session, tenant_id=..., created_by=..., filename="archsites.gml",
        content=content, collection_title="Sites", lat_field=None, lon_field=None,
    )
    assert result.item_id is not None  # géométrie présente -> Map créée


def test_run_import_jsonlines_no_geometry_creates_tabular_collection_without_map(session, ...):
    content = (Path(__file__).parent / "fixtures" / "ingestion" / "scifact_claims_sample.jsonl").read_bytes()
    result = run_import(
        session, tenant_id=..., created_by=..., filename="claims.jsonl",
        content=content, collection_title="Claims", lat_field=None, lon_field=None,
        geometry_mode="none",
    )
    assert result.item_id is None
    info = introspect_table(session, ...)  # récupérer table_name via collections_repo.get_collection
    assert info.geometry_column is None


def test_run_import_csv_wkt_mode_creates_geometry_collection(session, ...):
    content = b"name,wkt\nA,POINT (1 2)\n"
    result = run_import(
        session, tenant_id=..., created_by=..., filename="points.csv",
        content=content, collection_title="Points", lat_field=None, lon_field=None,
        geometry_mode="wkt", wkt_field="wkt",
    )
    assert result.item_id is not None
```

(`session`/fixtures de tenant/utilisateur suivent le patron déjà en vigueur
dans `test_ingestion_importer.py` — reprendre exactement la fixture
utilisée par les tests `run_import` existants pour GeoJSON/CSV plutôt que
d'en écrire une nouvelle.)

- [ ] **Step 9 : lancer toute la suite ingestion, vérifier le succès**

```bash
cd core && uv run pytest tests/test_ingestion_importer.py tests/test_ingestion_routes.py tests/test_ingestion_parsers.py -v
```

Attendu : tous passed.

- [ ] **Step 10 : commit**

```bash
git add core/app/ingestion/ core/tests/test_ingestion_importer.py \
  core/tests/test_ingestion_routes.py core/alembic/versions/
git commit -m "feat(core): câble tous les nouveaux formats dans run_import, table sans géométrie sans Map (GAP-29)"
```

---

## Task 12 : shell — `ImportFileButton.tsx`

**Files:**
- Modify: `shell/src/shell/ImportFileButton.tsx` (intégralement — phase
  renommée, sélecteur à 3 options, flux XLSX multi-feuilles à 2 appels,
  parquet `fields === null`, `poll()` sans `itemId`, `accept` étendu)
- Modify: `shell/src/api/types.ts`/`shell/src/api/base.ts` si
  `InspectResponse`/`IngestionJobCreate` (types générés TS) doivent être
  régénérés — **vérifier après la régénération OpenAPI de la Task 13, ne
  pas éditer les types générés à la main**
- Test: `shell/src/shell/ImportFileButton.test.tsx` (lire le fichier
  existant en entier d'abord pour reprendre le patron de mock
  `useItemClient`)

**Interfaces:**
- Consumes: `InspectResponse.fields: string[] | null`, `LayerInfo`,
  `IngestionJobCreate` (types shell, régénérés en Task 13 — utiliser les
  champs `wktField`/`geometryMode` en anticipant leur présence, ce fichier
  ne compile pas tant que la Task 13 n'a pas régénéré les types ; documenté
  comme dépendance explicite de cette tâche sur la Task 13, à rebours de
  l'ordre normal — cf. note Step 7).

- [ ] **Step 1 : renommer la phase `selecting-latlon` → `selecting-geometry`**

Dans `shell/src/shell/ImportFileButton.tsx` L11, remplacer :

```ts
type Phase = "form" | "uploading" | "selecting-layer" | "selecting-latlon" | "polling" | "error";
```

par :

```ts
type Phase = "form" | "uploading" | "selecting-layer" | "selecting-geometry" | "polling" | "error";
```

Remplacer toutes les occurrences de `"selecting-latlon"` par
`"selecting-geometry"` dans le fichier (comparaisons `phase ===`, appels
`setPhase(...)`).

- [ ] **Step 2 : écrire les tests du nouveau sélecteur à 3 options**

Lire `shell/src/shell/ImportFileButton.test.tsx` en entier d'abord (patron
de mock existant). Ajouter :

```tsx
test("selecting-geometry propose lat/lon, WKT et aucune géométrie", async () => {
  // reprendre le patron d'upload + inspectUpload mocké renvoyant
  // fields: ["name", "wkt_col"] sans lat/lon détectables
  ...
  render(<ImportFileButton />);
  // ... déclencher l'upload d'un .jsonl (ou tout format tabulaire)
  await screen.findByText(t("importFile.geometryModeNone")); // libellé à ajouter au catalogue i18n
  fireEvent.click(screen.getByLabelText(t("importFile.geometryModeNone")));
  fireEvent.click(screen.getByRole("button", { name: t("importFile.continueButton") }));
  await waitFor(() => expect(mockClient.createIngestionJob).toHaveBeenCalledWith(
    expect.objectContaining({ geometryMode: "none" }),
  ));
});

test("selecting-geometry en mode WKT envoie wktField", async () => {
  ...
  fireEvent.click(screen.getByLabelText(t("importFile.geometryModeWkt")));
  fireEvent.change(screen.getByLabelText(t("importFile.wktColumn")), { target: { value: "wkt_col" } });
  fireEvent.click(screen.getByRole("button", { name: t("importFile.continueButton") }));
  await waitFor(() => expect(mockClient.createIngestionJob).toHaveBeenCalledWith(
    expect.objectContaining({ geometryMode: "wkt", wktField: "wkt_col" }),
  ));
});
```

(Les clés i18n exactes `importFile.geometryModeNone`/
`importFile.geometryModeWkt`/`importFile.wktColumn` sont à ajouter au
catalogue `shell/src/i18n/catalog.fr.ts`, domaine `importFile.*` déjà en
usage dans ce fichier — cohérence de nommage avec les clés existantes
`importFile.latColumn`/`importFile.lonColumn`.)

- [ ] **Step 3 : lancer, vérifier l'échec**

```bash
cd shell && npm run test -- ImportFileButton -t "selecting-geometry"
```

Attendu : échec — le composant n'a pas encore de sélecteur de mode, envoie
toujours `latField`/`lonField`.

- [ ] **Step 4 : implémenter le sélecteur à 3 options**

Ajouter un state `geometryChoice: "latlon" | "wkt" | "none"` (défaut
`"latlon"`), un state `wktField: string`. Remplacer le bloc JSX
`selecting-latlon`/`selecting-geometry` (L241-283 avant cette tâche) par un
formulaire à 3 branches conditionnelles sur `geometryChoice` (boutons radio
ou `<select>` de mode, cf. spec §3.2) — reprendre le style Tailwind/kit déjà
utilisé pour les deux `<select>` existants (`h-9 rounded-md border
border-rule bg-surface px-3 text-sm text-ink`, convention `h-9` déjà en
vigueur, cf. CLAUDE.md conventions tranchées). Le bouton
`t("importFile.continueButton")` reste désactivé tant que le mode choisi
n'a pas ses champs requis (`latField && lonField` pour lat/lon, `wktField`
pour WKT, toujours activé pour "aucune géométrie").

Ajouter les clés au catalogue i18n (`shell/src/i18n/catalog.fr.ts`) :
`importFile.geometryModeLatLon`/`importFile.geometryModeWkt`/
`importFile.geometryModeNone`/`importFile.wktColumn` (libellés français
courts, ex. « Colonnes latitude/longitude », « Colonne WKT unique »,
« Aucune géométrie », « Colonne WKT »).

- [ ] **Step 5 : lancer, vérifier le succès**

```bash
cd shell && npm run test -- ImportFileButton -t "selecting-geometry"
```

Attendu : passed.

- [ ] **Step 6 : flux XLSX multi-feuilles (2 appels d'inspection)**

Écrire le test :

```tsx
test("XLSX multi-feuilles : selecting-layer puis inspection scopée à la feuille choisie", async () => {
  mockClient.inspectUpload
    .mockResolvedValueOnce({ layers: [{ name: "Feuil1", featureCount: 3, geometryType: "Tabular" },
                                       { name: "Feuil2", featureCount: 5, geometryType: "Tabular" }], fields: null })
    .mockResolvedValueOnce({ layers: [], fields: ["lat", "lon"] });
  render(<ImportFileButton />);
  // upload .xlsx, choisir "Feuil1" dans selecting-layer
  ...
  await waitFor(() => expect(mockClient.inspectUpload).toHaveBeenNthCalledWith(
    2, expect.objectContaining({ layerName: "Feuil1" }),
  ));
  // lat/lon détectés sur cette feuille -> job direct
  await waitFor(() => expect(mockClient.createIngestionJob).toHaveBeenCalledWith(
    expect.objectContaining({ layerName: "Feuil1" }),
  ));
});
```

Lancer, vérifier l'échec. Implémenter : dans `confirmLayer()` (L191-203
avant cette tâche), après confirmation d'une feuille XLSX (à distinguer des
gpkg/kml/gml natifs par un check sur l'extension du fichier — `.xlsx`
seulement), appeler un 2e `inspectUpload({ key: uploadedKey, filename:
file.name, layerName })`, puis brancher sur `detectLatLon(fields ?? [])`
exactement comme le flux mono-feuille existant. Introduire un helper
`isTabularSheetFormat(filename)` (vrai pour `.xlsx` seulement) pour cette
distinction, distinct de `isLayeredFormat` (gpkg/zip/kml/kmz/gml — géométrie
déjà native, jamais de second appel d'inspection après le choix de couche).

- [ ] **Step 7 : parquet — distinguer `fields === null`**

Écrire le test :

```tsx
test("parquet géo-référencé (fields=null) démarre le job sans étape de géométrie", async () => {
  mockClient.inspectUpload.mockResolvedValueOnce({ layers: [], fields: null });
  render(<ImportFileButton />);
  // upload .parquet
  ...
  await waitFor(() => expect(mockClient.createIngestionJob).toHaveBeenCalled());
  expect(screen.queryByText(t("importFile.geometryModeNone"))).not.toBeInTheDocument();
});
```

Lancer, vérifier l'échec (`.parquet` ne passe aujourd'hui par aucune
inspection). Étendre `needsFieldInspection(filename)` (L39-41) pour inclure
`.jsonl`, `.xml`, `.parquet` (en plus de `.xlsx`, qui migre vers
`isTabularSheetFormat` du Step 6 — **retirer `.xlsx` de
`needsFieldInspection`**, remplacé par le flux dédié du Step 6). Dans
`submit()` (L149-189), après l'appel `inspectUpload` pour ces formats,
brancher :

```ts
if (found_fields === null) {
  await startJob(key, undefined);
} else if (!detectLatLon(found_fields)) {
  setCsvHeaders(found_fields);
  setPhase("selecting-geometry");
} else {
  await startJob(key, undefined);
}
```

(`found_fields` = le nom réel de la variable déstructurée depuis
`inspectUpload`, à adapter au code existant — actuellement `const { fields
} = await client.inspectUpload(...)`, garder ce nom.)

- [ ] **Step 8 : lancer, vérifier le succès**

```bash
cd shell && npm run test -- ImportFileButton
```

Attendu : tous passed (fichier de test complet).

- [ ] **Step 9 : `isLayeredFormat` gagne `.gml`, `accept` étendu**

```ts
function isLayeredFormat(filename: string): boolean {
  const lower = filename.toLowerCase();
  return (
    lower.endsWith(".gpkg") ||
    lower.endsWith(".zip") ||
    lower.endsWith(".kml") ||
    lower.endsWith(".kmz") ||
    lower.endsWith(".gml")
  );
}
```

`accept=".geojson,.json,.csv,.xlsx,.kml,.kmz,.gpkg,.zip,.parquet"` (L318) →
`accept=".geojson,.json,.csv,.xlsx,.kml,.kmz,.gpkg,.zip,.parquet,.jsonl,.gml,.xml"`.

- [ ] **Step 10 : `poll()` gère `status === "done"` sans `itemId`**

Écrire le test :

```tsx
test("job terminé sans itemId (collection sans géométrie) ferme le tiroir et navigue vers /admin/collections", async () => {
  mockClient.getIngestionJob.mockResolvedValueOnce({ status: "done", itemId: null, errorMessage: null, collectionId: "c1" });
  ...
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/admin/collections"));
});
```

Lancer, vérifier l'échec (actuellement, `poll()` boucle indéfiniment sur ce
cas — le test doit soit timeout, soit révéler l'absence de navigation).
Modifier `poll()` (L114-134) :

```ts
async function poll(jobId: string) {
  for (;;) {
    if (!mountedRef.current) return;
    const job = await client.getIngestionJob(jobId);
    if (!mountedRef.current) return;
    if (job.status === "done") {
      close();
      navigate(job.itemId ? `/maps/${job.itemId}` : "/admin/collections");
      return;
    }
    if (job.status === "error") {
      setPhase("error");
      setError(job.errorMessage ?? t("importFile.genericError"));
      return;
    }
    await new Promise<void>((resolve) => {
      timerRef.current = setTimeout(resolve, 1500);
    });
    if (!mountedRef.current) return;
  }
}
```

- [ ] **Step 11 : lancer toute la suite du fichier, vérifier le succès**

```bash
cd shell && npm run test -- ImportFileButton
```

Attendu : tous passed, y compris les tests existants non touchés par cette
tâche (aucune régression sur GeoJSON/CSV/GPKG/KML/KMZ/XLSX mono-feuille/
GeoParquet déjà couverts).

- [ ] **Step 12 : commit**

```bash
git add shell/src/shell/ImportFileButton.tsx shell/src/shell/ImportFileButton.test.tsx \
  shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): étend ImportFileButton aux nouveaux formats et au choix de géométrie à 3 options (GAP-29)"
```

**Note sur l'ordre des tâches** : cette tâche référence des champs TS
(`wktField`/`geometryMode` sur `IngestionJobCreate`, `fields: string[] |
null` sur `InspectResponse`) qui ne sont formellement régénérés dans
`shell/src/api/generated/core-schema.d.ts` qu'à la Task 13. Si le typage TS
du client (`shell/src/api/types.ts`/`base.ts`) est déjà assez lâche pour
accepter ces champs en écriture sans régénération (à vérifier — certains
projets utilisent des types manuels non générés pour le payload de requête,
d'autres non), cette tâche compile déjà ; sinon, régénérer les types dès
cette tâche (avancer une partie du Step 1 de la Task 13) plutôt que de
laisser le shell dans un état qui ne compile pas entre les deux tâches.

---

## Task 13 : clôture — régénération, inventaire, suites complètes, `CLAUDE.md`

**Files:**
- Modify: `core/openapi.json` (régénéré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `docs/revue/2026-09-04-analyse-gaps.md` (GAP-29 : ouvert → fermé,
  référence à ce chantier)
- Modify: `docs/revue/2026-09-04-backlog.md` (si une entrée `REV-nnn`
  concerne ce gap — vérifier, sinon ne rien ajouter)
- Modify: `CLAUDE.md` (une ligne dans `### Livré`, ne pas renuméroter le
  backlog)
- Verify: `core/tests/test_feature_inventory.py`,
  `core/scripts/feature_health_cli.py --check`

**Interfaces:**
- Consumes: l'ensemble des tâches précédentes.
- Produces: aucun nouveau code — clôture uniquement.

- [ ] **Step 1 : régénérer OpenAPI + types TS**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Attendu : diff **non vide**, cohérent avec les champs ajoutés
(`InspectRequest.layerName`, `IngestionJobCreate.wktField`/`geometryMode`)
— aucune route nouvelle, uniquement des schémas étendus (cf. critère
d'acceptation 10 de la spec).

- [ ] **Step 2 : suite complète cœur**

```bash
cd core && uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```

Attendu : tous verts, couverture non régressive (comparer au dernier
chiffre connu dans `CLAUDE.md`, actuellement 94,05 % avant ce plan — un
écart de quelques dixièmes sans rapport avec ce plan doit être vérifié en
isolation avant d'être imputé à ce plan, cf. piège CLAUDE.md n°9 sur la
contention de sessions concurrentes).

- [ ] **Step 3 : suite complète shell**

```bash
cd shell && rm -rf dist dist-export && npm run test
npm run lint && npm run format:check
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run build
```

Attendu : tous verts. Si `npm run e2e` couvre `ImportFileButton` (vérifier
`shell/e2e/` pour un spec d'ingestion existant, ex.
`ingestion-gpkg.spec.ts` mentionné par SP-60) : le rejouer aussi, et
envisager d'y ajouter un scénario minimal pour un des nouveaux formats
(au choix de l'exécutant — non bloquant si le budget E2E de ce plan ne le
prévoit pas explicitement, mais à documenter si omis).

- [ ] **Step 4 : vérifier l'inventaire de fonctionnalités**

```bash
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check
```

Attendu : vert sans modification de
`docs/revue/inventaire-fonctionnalites.jsonl` (aucune route REST/outil MCP/
route shell nouvelle — uniquement des formats supplémentaires sur
`POST /uploads`/`POST /uploads/inspect`, déjà inventoriées). Si le
`--check` échoue en signalant une surface non inventoriée : investiguer
avant de supposer un faux positif (vérifier si une route a été ajoutée par
erreur, ex. Step 1/2 de Task 11 si une migration a introduit une route
d'administration non prévue par la spec — ne devrait pas être le cas ici).

- [ ] **Step 5 : mettre à jour `docs/revue/2026-09-04-analyse-gaps.md`**

Repérer la ligne `GAP-29` dans le tableau d'état, la faire passer de
`ouvert` à `fermé`, ajouter une référence à ce chantier (date, chemins de
la spec/du plan).

- [ ] **Step 6 : mettre à jour `CLAUDE.md`**

Ajouter une entrée dans `### Livré`, format cohérent avec les entrées
existantes (ex. SP-56 juste au-dessus) :

```markdown
- **GAP-29 (reste)** — 6 formats d'import supplémentaires : Excel
  multi-feuilles (réutilise `selecting-layer`), Parquet non-géo (sniff de
  la clé `"geo"`), JSON Lines, CSV/WKT, GML/INSPIRE (traité comme KML),
  XML générique (heuristique d'élément répété, `defusedxml`). Fonction
  pivot partagée `extract_geometry`/`GeometryMode` (lat/lon | WKT |
  aucune) — évite de dupliquer le choix de géométrie par parseur. Une
  collection sans géométrie ne crée plus de Map/Item/Config (précédent :
  `register_collection`, le flux admin, ne le faisait déjà pas) ;
  `ImportFileButton` navigue vers `/admin/collections` dans ce cas au lieu
  de rester en sondage infini. Fixtures de test réelles téléchargées
  (GDAL/Apache POI/OpenAI cookbook/Microsoft Aspire, licences
  MIT/Apache-2.0 vérifiées) plutôt que synthétiques, sous
  `core/tests/fixtures/ingestion/`. [Compléter après exécution : suite
  finale mesurée, écarts trouvés par exécution vs. le texte de ce plan,
  cf. piège CLAUDE.md n°3.]
```

(Le texte entre crochets doit être remplacé par les faits réels observés
pendant l'exécution — ne pas laisser un placeholder dans le commit final.)

- [ ] **Step 7 : commit final**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts \
  docs/revue/2026-09-04-analyse-gaps.md CLAUDE.md
git commit -m "docs: clôture GAP-29 — formats d'import supplémentaires"
```

---

## Self-Review (à exécuter par la session qui écrit ce plan, déjà faite ici)

**Couverture de la spec** : §0/§2.1 → Task 2-4 ; §2.2 → Task 5 ; §2.3 →
Task 9 ; §2.4 → Task 8 ; §2.5 → Task 3 ; §2.6 → Task 7 ; §2.7 → Task 10 ;
§2.8/§2.9 → Task 11 ; §3 → Task 12 ; §4 (fixtures) → Task 1 ; §5 (critères
d'acceptation) → répartis, tous couverts par au moins une tâche ; §6 (hors
périmètre) → aucune tâche n'implémente XPath/INSPIRE dédié/rendu carte
sans géométrie/2e langue, conforme.

**Placeholders** : aucun "TBD"/"à compléter plus tard" dans le corps des
tâches, à l'exception du texte explicitement marqué comme à remplacer par
un fait observé (Task 13 Step 6, CLAUDE.md — inévitable pour une entrée de
clôture qui documente le résultat d'une exécution qui n'a pas encore eu
lieu au moment d'écrire ce plan).

**Cohérence des types/signatures** : `GeometryMode`/`extract_geometry`
(Task 2) utilisés à l'identique par Tasks 3/4/8/9/10/11 ; `parse_xlsx_sheet`
(renommé Task 4) utilisé par Task 5 et Task 11, jamais réutilisé sous
l'ancien nom `parse_xlsx_latlon` après la Task 4 ; `ImportResult.item_id:
str | None` (Task 11) est le type que consomme Task 12 (`job.itemId` côté
shell, déjà `str | null` généré depuis `IngestionJobStatus.itemId: str |
None`, inchangé) ; `_rename_reserved_property_keys` (Task 6) utilisé avec
les préfixes `"kml"` (Task 6, refactor), `"gml"` (Task 7), `"jsonl"`
(Task 8), `"xml"` (Task 10) — aucune divergence de nom entre les tâches.
