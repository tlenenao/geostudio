# IPC d'échange DuckDB↔futurs moteurs natifs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser, côté `core` uniquement, le seam d'échange DuckDB↔futurs moteurs natifs (Arrow zéro-copie + GeoParquet natif en repli) que le prochain chantier « premier moteur natif » consommera — sans câbler aucun moteur réel et sans toucher à `transform.qgis`.

**Architecture:** Un nouveau module `app/pipelines/exchange.py` expose deux fonctions publiques (`to_arrow_stream`/`from_arrow_stream`, chemin zéro-copie) et un helper de repli fichier (`to_geoparquet_file`), qui délègue sa primitive d'écriture réelle à une fonction ajoutée dans `app/cdc/parquet_writer.py` (`write_geoparquet_from_relation`) — jamais un second writer Parquet réinventé. `OperationContract` (`app/pipelines/ops/contracts.py`) gagne un champ additif `exchange`, jamais consommé par `runtime.py` dans ce chantier.

**Tech Stack:** Python 3.12, DuckDB (extension `spatial`), PyArrow, GeoPandas/Shapely — toutes des dépendances déjà présentes dans `core/pyproject.toml`, aucun ajout.

## Global Constraints

- **QGIS hors périmètre absolu** : aucun changement à `transform.qgis`/`app/pipelines/runtime.py`/`_execute_qgis_transform`/`_materialize_qgis_output`. Le GDAL 3.4.1 embarqué par `qgis/qgis:release-3_34` n'a aucun driver Parquet/Arrow (vérifié empiriquement, design §1) — ce chantier ne peut rien y changer.
- **Aucun moteur natif câblé** dans ce chantier (pas de GDAL/PDAL/OTB/Rust réel, pas de nouvel import de binding).
- **Aucune nouvelle op ni transformer.**
- **`exchange` n'est consommé par aucun code d'exécution réel** : pas de branche `if contract.exchange == ...` dans `runtime.py`. Le champ existe, rien ne le lit encore.
- **Round-trip Arrow jamais invoqué depuis `runtime.py`** — validé uniquement par ses propres tests unitaires.
- **`srid` est un paramètre obligatoire** de `to_arrow_stream`/`to_geoparquet_file`, jamais optionnel — sans lui, `.arrow()` renvoie des métadonnées CRS vides (`{}`), vérifié empiriquement (design §1).
- **Détection de la colonne géométrie par TYPE DuckDB (`GEOMETRY`), jamais par nom** — même garantie que `_materialize_reader`/`_materialize_qgis_output` (`app/pipelines/runtime.py`).
- **Erreur propre `PipelineRuntimeError`** (pas de `KeyError`/`IndexError` silencieux) si la relation ne porte aucune colonne géométrie — même contrat que `_materialize_qgis_output`.
- **Aucun changement d'API publique** : `exchange` n'entre jamais dans `ops_catalog()`/`GET /pipelines/ops`. Diff `openapi.json`/`core-schema.d.ts` attendu **vide** — à vérifier, jamais supposé.
- **Zéro fichier `shell/` touché** (chantier `core-only`, cf. titre du design) — à vérifier, jamais supposé.
- **Suite des 19 op existantes inchangée** : diff de comportement nul, aucune régression sur `test_pipeline_ops_contracts.py`/`test_pipeline_ops_schemas.py`/`test_pipeline_routes.py`/`test_pipeline_runtime.py`/`test_pipeline_compiler.py`/`test_cdc_parquet_writer.py`.
- **`from_arrow_stream(conn, reader, ...)` exige une connexion DuckDB différente de celle qui a produit `relation`/`reader` passés à `to_arrow_stream`** — trouvaille empirique de ce plan (absente du design, cf. section dédiée ci-dessous) : enregistrer sur `conn` un `RecordBatchReader` non-drainé produit par CETTE MÊME connexion, puis exécuter une requête dessus, **deadlocke** `conn.execute()` indéfiniment (pas d'erreur, un vrai blocage — reproduit et confirmé avec `timeout`). Aucun test de ce plan ne doit jamais appeler `to_arrow_stream(rel, ...)` puis `from_arrow_stream(conn, reader, ...)` avec `rel`/`reader` et `conn` issus de la **même** connexion source.

## Décision prise en amont (risque §5 du design, tranchée ici plutôt que laissée ouverte)

Le design flaggait un risque : « adapter `write_geoparquet(rows: list[ChangeRow], ...)` pour qu'il accepte une relation DuckDB arbitraire, sinon écrire un writer parallèle minimal qui appelle les mêmes primitives internes ». Vérifié en amont de ce plan (empiriquement, pas supposé) : `build_geodataframe(rows: list[ChangeRow], ...)` ajoute systématiquement 4 colonnes de plomberie CDC à chaque enregistrement (`_op`, `_lsn`, `_seq`, `_ts`, cf. `app/cdc/parquet_writer.py:41-45`) — router une relation de pipeline générique à travers `ChangeRow` ferait donc apparaître ces 4 colonnes fantômes dans tout GeoParquet produit par `to_geoparquet_file`, ce qui **casse** l'exigence du design §2 (« round-trip identité, schéma... préservés »). L'adaptation de signature est donc jugée trop intrusive : ce plan écrit deux fonctions sœurs (`build_geodataframe_from_relation`/`write_geoparquet_from_relation`) dans le même fichier `app/cdc/parquet_writer.py`, qui convergent avec le chemin CDC existant sur **une seule primitive d'écriture réelle** (`_write_gdf`, `GeoDataFrame.to_parquet` appelé à exactement un seul endroit du fichier) — vérifié par un test dédié (Task 1, Step 1).

## Risque supplémentaire trouvé en vérifiant (absent du texte du design)

En prototypant `from_arrow_stream` avant d'écrire ce plan (piège CLAUDE.md n°3 : vérifier empiriquement, jamais supposer), un deadlock réel a été reproduit — confirmé sous `timeout`, pas une simple erreur DuckDB : enregistrer (`conn.register`) sur une connexion DuckDB `conn` un `pyarrow.RecordBatchReader` **non drainé** produit par `.arrow()` sur **cette même connexion** `conn`, puis exécuter une requête (`conn.execute("CREATE TEMP TABLE ... AS SELECT * FROM ...")`) qui lit ce flux, bloque indéfiniment `conn.execute()`. Avec **deux connexions distinctes** (la relation source construite sur une connexion, `from_arrow_stream` appelé sur une autre), le même enchaînement fonctionne instantanément (vérifié à plusieurs reprises). Aucune garde runtime possible côté `from_arrow_stream` (un `RecordBatchReader` ne permet pas d'introspecter la connexion DuckDB qui l'a produit) — documenté dans son docstring (Task 2, Step 3) comme une contrainte d'appel, pas un bug à corriger. Tous les tests de ce plan qui exercent `to_arrow_stream`+`from_arrow_stream` ensemble utilisent donc systématiquement deux connexions distinctes.

---

### Task 1: `app/cdc/parquet_writer.py` — écriture GeoParquet depuis une relation DuckDB arbitraire

**Files:**
- Modify: `core/app/cdc/parquet_writer.py`
- Test: `core/tests/test_cdc_parquet_writer.py`

**Interfaces:**
- Consumes: rien de nouveau — réutilise `geopandas`/`shapely.wkb` déjà importés dans ce fichier.
- Produces (consommé par Task 2) :
  - `write_geoparquet_from_relation(relation: duckdb.DuckDBPyRelation, *, srid: int, geometry_column: str, path: str) -> None`
  - `build_geodataframe_from_relation(relation: duckdb.DuckDBPyRelation, *, srid: int, geometry_column: str) -> gpd.GeoDataFrame` (exposée pour test direct)

- [ ] **Step 1: Écrire le test qui échoue — round-trip depuis une relation DuckDB**

Éditer `core/tests/test_cdc_parquet_writer.py`. Remplacer le bloc d'imports en tête de fichier :

```python
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import UTC, datetime
from decimal import Decimal

import geopandas as gpd
import pandas as pd
import shapely.wkb
from shapely.geometry import Point

from app.analytics.duckdb_conn import open_spatial_connection
from app.cdc import parquet_writer
from app.cdc.backfill import _normalize_record
from app.cdc.consumer import decode_wal2json_message
from app.cdc.parquet_writer import (
    ChangeRow,
    build_geodataframe,
    build_geodataframe_from_relation,
    write_geoparquet,
    write_geoparquet_from_relation,
)
```

Ajouter en fin de fichier :

```python
def test_build_geodataframe_from_relation_preserves_schema_crs_and_values():
    conn = open_spatial_connection()
    rel = conn.sql(
        "SELECT 1 AS id, ST_Point(700000, 6600000) AS geom, 'a' AS name "
        "UNION ALL SELECT 2, ST_Point(700100, 6600100), 'b'"
    )
    gdf = build_geodataframe_from_relation(rel, srid=2154, geometry_column="geom")
    assert list(gdf["id"]) == [1, 2]
    assert list(gdf["name"]) == ["a", "b"]
    assert gdf.crs.to_epsg() == 2154
    assert gdf.geometry.iloc[0].equals(Point(700000, 6600000))
    assert gdf.geometry.iloc[1].equals(Point(700100, 6600100))


def test_write_geoparquet_from_relation_round_trip(tmp_path):
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, ST_Point(700000, 6600000) AS geom, 'a' AS name")
    path = str(tmp_path / "relation.parquet")
    write_geoparquet_from_relation(rel, srid=2154, geometry_column="geom", path=path)

    gdf = gpd.read_parquet(path)
    assert list(gdf.columns) == ["id", "name", "geometry"]
    assert gdf.crs.to_epsg() == 2154
    assert gdf.geometry.iloc[0].equals(Point(700000, 6600000))


def test_write_geoparquet_from_relation_with_no_other_columns():
    # cas limite : une relation ne portant QUE la géométrie (aucune colonne
    # métier) — other_cols vide, ne doit pas planter le zip().
    conn = open_spatial_connection()
    rel = conn.sql("SELECT ST_Point(1, 2) AS geom")
    gdf = build_geodataframe_from_relation(rel, srid=4326, geometry_column="geom")
    assert list(gdf.columns) == ["geometry"]
    assert gdf.geometry.iloc[0].equals(Point(1, 2))


def test_write_geoparquet_and_write_geoparquet_from_relation_share_the_writer_primitive(
    monkeypatch, tmp_path
):
    # Preuve de non-duplication (design §2) : les deux chemins d'écriture
    # (ChangeRow CDC / relation DuckDB générique) doivent converger sur
    # EXACTEMENT la même primitive d'écriture Parquet, jamais deux appels
    # indépendants à GeoDataFrame.to_parquet.
    calls: list[str] = []
    original = parquet_writer._write_gdf

    def spy(gdf, path):
        calls.append(path)
        return original(gdf, path)

    monkeypatch.setattr(parquet_writer, "_write_gdf", spy)

    write_geoparquet(
        [
            ChangeRow(
                op="insert",
                lsn=1,
                ts=1.0,
                pk_column="id",
                pk_value=1,
                columns={"id": 1},
                geometry_column="geom",
                geometry_wkb_hex=shapely.wkb.dumps(Point(1, 2), hex=True),
            )
        ],
        srid=4326,
        path=str(tmp_path / "cdc.parquet"),
    )
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, ST_Point(1, 2) AS geom")
    write_geoparquet_from_relation(
        rel, srid=4326, geometry_column="geom", path=str(tmp_path / "relation.parquet")
    )

    assert len(calls) == 2
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `cd core && uv run pytest tests/test_cdc_parquet_writer.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_geodataframe_from_relation' from 'app.cdc.parquet_writer'` (les 4 nouveaux tests échouent, les tests existants du fichier ne sont pas encore collectés à cause de l'ImportError).

- [ ] **Step 3: Implémenter `build_geodataframe_from_relation`/`write_geoparquet_from_relation`**

Remplacer le contenu de `core/app/cdc/parquet_writer.py` en entier par :

```python
# SPDX-License-Identifier: Apache-2.0
"""Écriture GeoParquet 1.0 pour les lots de changements CDC (SP-11a §Format
de sortie) : append-only change log, jamais un état fusionné. Une ligne
"delete" est une tombstone — seules la PK et _op sont renseignées (REPLICA
IDENTITY par défaut n'expose que la PK sur delete, pas besoin de REPLICA
IDENTITY FULL). Pas de reprojection : le SRID source (Collection.srid) est
passé tel quel par l'appelant et posé comme CRS de sortie.

build_geodataframe_from_relation/write_geoparquet_from_relation (design
docs/superpowers/specs/2026-09-16-ipc-echange-duckdb-arrow-design.md) :
chemin de repli GeoParquet consommé par app.pipelines.exchange.
to_geoparquet_file, pour une relation DuckDB arbitraire — jamais un
ChangeRow, dont les colonnes de plomberie CDC (_op/_lsn/_seq/_ts,
tombstones) n'ont pas de sens pour une relation de pipeline générique et
casseraient l'identité de schéma attendue par un round-trip GeoParquet
(cf. plan, section "Décision prise en amont"). Les deux chemins convergent
malgré tout sur UNE seule primitive d'écriture réelle (_write_gdf) :
jamais un writer Parquet réinventé."""

from dataclasses import dataclass

import duckdb
import geopandas as gpd
import shapely.wkb
from shapely.geometry.base import BaseGeometry


@dataclass
class ChangeRow:
    op: str  # "insert" | "update" | "delete"
    lsn: int
    ts: float  # horloge murale d'écriture du FLUSH (pas l'horodatage wal2json)
    pk_column: str
    pk_value: object
    columns: dict  # colonnes métier ; {pk_column: pk_value} seulement si op == "delete"
    geometry_column: str | None
    geometry_wkb_hex: str | None  # hex EWKB ; None pour une tombstone ou une table sans géométrie
    # Ordre d'ajout réel au buffer CDC (CdcBufferManager.add(), monotone,
    # affecté APRÈS construction — cf. app.cdc.buffer). Départage un `_lsn`
    # ex-aequo (app.cdc.consumer:54-70 : le settle peut tagger deux
    # transactions distinctes avec la même LSN) dans app.analytics.aggregate
    # ._dedup_cte. 0 par défaut pour les chemins qui n'écrivent jamais deux
    # versions de la même PK (ex. app.appexport.snapshot, un seul insert par
    # PK) : aucun ex-aequo possible là, donc aucun besoin de départage.
    seq: int = 0


def _decode_geometry(wkb_hex: str | None) -> BaseGeometry | None:
    if wkb_hex is None:
        return None
    return shapely.wkb.loads(bytes.fromhex(wkb_hex))


def build_geodataframe(rows: list[ChangeRow], *, srid: int) -> gpd.GeoDataFrame:
    records = []
    geometries = []
    for row in rows:
        record = dict(row.columns)
        record[row.pk_column] = row.pk_value
        record["_op"] = row.op
        record["_lsn"] = row.lsn
        record["_seq"] = row.seq
        record["_ts"] = row.ts
        records.append(record)
        geometries.append(_decode_geometry(row.geometry_wkb_hex))
    crs = f"EPSG:{srid}" if srid else None
    return gpd.GeoDataFrame(records, geometry=geometries, crs=crs)


def _write_gdf(gdf: gpd.GeoDataFrame, path: str) -> None:
    # Seul endroit du fichier qui appelle GeoDataFrame.to_parquet — les deux
    # chemins publics (write_geoparquet CDC, write_geoparquet_from_relation
    # générique) convergent ici, jamais un writer dupliqué.
    gdf.to_parquet(path)


def write_geoparquet(rows: list[ChangeRow], *, srid: int, path: str) -> None:
    gdf = build_geodataframe(rows, srid=srid)
    _write_gdf(gdf, path)


def _qi(name: str) -> str:
    # Duplication délibérée du helper de 2 lignes présent dans
    # app.analytics.aggregate/app.pipelines.compiler/app.pipelines.runtime —
    # convention déjà actée dans ce dépôt (cf. app.pipelines.runtime._qi),
    # pas un import inter-module d'un nom privé `_`-préfixé.
    return '"' + name.replace('"', '""') + '"'


def build_geodataframe_from_relation(
    relation: duckdb.DuckDBPyRelation, *, srid: int, geometry_column: str
) -> gpd.GeoDataFrame:
    """Même sortie que build_geodataframe (une gpd.GeoDataFrame) mais lue
    directement depuis une relation DuckDB plutôt qu'un tampon ChangeRow —
    geometry_column est déjà résolue par l'appelant (détection par type
    DuckDB GEOMETRY, cf. app.pipelines.exchange._geometry_column), jamais
    redevinée ici. Décodage WKB brut (pas hex) : ST_AsWKB renvoie des bytes
    Python directement exploitables par shapely.wkb.loads, contrairement au
    chemin CDC qui transporte du hex EWKB (_decode_geometry) — deux
    encodages légitimement différents, pas une divergence à unifier."""
    other_cols = [c for c in relation.columns if c != geometry_column]
    select_list = ", ".join(
        [_qi(c) for c in other_cols] + [f"ST_AsWKB({_qi(geometry_column)}) AS {_qi('__wkb')}"]
    )
    rows = relation.select(select_list).fetchall()
    records = []
    geometries = []
    for row in rows:
        values = dict(zip(other_cols, row[:-1], strict=True))
        wkb = row[-1]
        records.append(values)
        geometries.append(shapely.wkb.loads(bytes(wkb)) if wkb is not None else None)
    crs = f"EPSG:{srid}" if srid else None
    return gpd.GeoDataFrame(records, geometry=geometries, crs=crs)


def write_geoparquet_from_relation(
    relation: duckdb.DuckDBPyRelation, *, srid: int, geometry_column: str, path: str
) -> None:
    gdf = build_geodataframe_from_relation(relation, srid=srid, geometry_column=geometry_column)
    _write_gdf(gdf, path)
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `cd core && uv run pytest tests/test_cdc_parquet_writer.py -v`
Expected: PASS — tous les tests (existants + les 4 nouveaux) passent.

- [ ] **Step 5: Commit**

```bash
cd core
git add app/cdc/parquet_writer.py tests/test_cdc_parquet_writer.py
git commit -m "$(cat <<'EOF'
feat(core): écriture GeoParquet native depuis une relation DuckDB arbitraire

Ajoute build_geodataframe_from_relation/write_geoparquet_from_relation à
app.cdc.parquet_writer — chemin de repli pour app.pipelines.exchange
(suite d'OperationContract). Écarté du ChangeRow existant (colonnes de
plomberie CDC incompatibles avec l'identité de schéma requise) mais
convergent sur la même primitive d'écriture (_write_gdf).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `app/pipelines/exchange.py` — Arrow zéro-copie + repli GeoParquet

**Files:**
- Create: `core/app/pipelines/exchange.py`
- Test: `core/tests/test_pipeline_exchange.py`

**Interfaces:**
- Consumes: `write_geoparquet_from_relation` (Task 1), `PipelineRuntimeError` (`app.pipelines.runtime`, déjà existant).
- Produces (aucun consommateur dans ce chantier — cf. Global Constraints) :
  - `to_arrow_stream(relation: duckdb.DuckDBPyRelation, *, srid: int) -> pyarrow.RecordBatchReader`
  - `from_arrow_stream(conn: duckdb.DuckDBPyConnection, reader: pyarrow.RecordBatchReader, *, view_name: str) -> None`
  - `to_geoparquet_file(relation: duckdb.DuckDBPyRelation, *, srid: int, path: str) -> None`

- [ ] **Step 1: Écrire le test qui échoue**

Créer `core/tests/test_pipeline_exchange.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import json

import geopandas as gpd
import pyarrow
import pytest
from shapely.geometry import Point

from app.analytics.duckdb_conn import open_spatial_connection
from app.pipelines.exchange import from_arrow_stream, to_arrow_stream, to_geoparquet_file
from app.pipelines.runtime import PipelineRuntimeError


def test_to_arrow_stream_embeds_projjson_crs_metadata():
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, ST_Point(700000, 6600000) AS geom")
    reader = to_arrow_stream(rel, srid=2154)
    table = reader.read_all()
    field = table.schema.field("geom")
    assert field.metadata[b"ARROW:extension:name"] == b"geoarrow.wkb"
    crs_meta = json.loads(field.metadata[b"ARROW:extension:metadata"])
    assert crs_meta["crs"]["id"] == {"authority": "EPSG", "code": 2154}


def test_to_arrow_stream_raises_on_relation_without_geometry_column():
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, 'a' AS name")
    with pytest.raises(PipelineRuntimeError, match="aucune colonne géométrie"):
        to_arrow_stream(rel, srid=4326)


def test_to_geoparquet_file_raises_on_relation_without_geometry_column(tmp_path):
    conn = open_spatial_connection()
    rel = conn.sql("SELECT 1 AS id, 'a' AS name")
    with pytest.raises(PipelineRuntimeError, match="aucune colonne géométrie"):
        to_geoparquet_file(rel, srid=4326, path=str(tmp_path / "x.parquet"))


def test_arrow_round_trip_preserves_schema_crs_and_values():
    source_conn = open_spatial_connection()
    rel = source_conn.sql(
        "SELECT 1 AS id, ST_Point(700000, 6600000) AS geom, 'a' AS name "
        "UNION ALL SELECT 2, ST_Point(700100, 6600100), 'b'"
    )
    reader = to_arrow_stream(rel, srid=2154)

    target_conn = open_spatial_connection()
    from_arrow_stream(target_conn, reader, view_name="rt")

    rows = target_conn.sql("SELECT id, ST_AsText(geom) AS wkt, name FROM rt ORDER BY id").fetchall()
    assert rows == [
        (1, "POINT (700000 6600000)", "a"),
        (2, "POINT (700100 6600100)", "b"),
    ]
    desc = {d[0]: d[1] for d in target_conn.sql("SELECT * FROM rt LIMIT 0").description}
    assert str(desc["geom"]) == "GEOMETRY('EPSG:2154')"


def test_geoparquet_file_round_trip_preserves_schema_crs_and_values(tmp_path):
    conn = open_spatial_connection()
    rel = conn.sql(
        "SELECT 1 AS id, ST_Point(700000, 6600000) AS geom, 'a' AS name "
        "UNION ALL SELECT 2, ST_Point(700100, 6600100), 'b'"
    )
    path = str(tmp_path / "roundtrip.parquet")
    to_geoparquet_file(rel, srid=2154, path=path)

    gdf = gpd.read_parquet(path)
    assert list(gdf["id"]) == [1, 2]
    assert list(gdf["name"]) == ["a", "b"]
    assert gdf.crs.to_epsg() == 2154
    assert gdf.geometry.iloc[0].equals(Point(700000, 6600000))
    assert gdf.geometry.iloc[1].equals(Point(700100, 6600100))


def test_from_arrow_stream_unregisters_its_internal_arrow_source():
    # from_arrow_stream doit unregister son nom temporaire interne même en
    # cas de succès — sinon un register() ultérieur sur ce même nom
    # échouerait en "already registered". Important : la relation source et
    # from_arrow_stream() utilisent ici DEUX connexions distinctes
    # (other_conn / conn) — jamais la même (cf. plan, section "Risque
    # supplémentaire trouvé en vérifiant" : réutiliser la même connexion
    # pour la relation source ET l'appel from_arrow_stream deadlocke
    # conn.execute(), vérifié empiriquement).
    conn = open_spatial_connection()
    other_conn = open_spatial_connection()
    rel = other_conn.sql("SELECT 1 AS id, ST_Point(1, 2) AS geom")
    reader = to_arrow_stream(rel, srid=4326)
    from_arrow_stream(conn, reader, view_name="rt1")
    assert conn.sql("SELECT id FROM rt1").fetchone() == (1,)

    conn.register("__exchange_arrow_src_rt1", pyarrow.table({"x": [1]}))
    conn.unregister("__exchange_arrow_src_rt1")
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `cd core && uv run pytest tests/test_pipeline_exchange.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.exchange'`

- [ ] **Step 3: Implémenter `app/pipelines/exchange.py`**

Créer `core/app/pipelines/exchange.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Échange DuckDB↔futurs moteurs natifs — Arrow zéro-copie + GeoParquet
natif en repli (design docs/superpowers/specs/
2026-09-16-ipc-echange-duckdb-arrow-design.md). Suite d'OperationContract
(docs/superpowers/specs/2026-09-16-operation-contract-design.md) : pose le
seam d'échange (champ OperationContract.exchange, app.pipelines.ops.
contracts) qu'un futur chantier "premier moteur natif" consommera — QGIS
(transform.qgis) reste explicitement hors périmètre, son échange fichier
GPKG (app.pipelines.runtime._execute_qgis_transform/_materialize_qgis_
output) n'est pas unifié avec ce module (aucun driver Parquet/Arrow dans le
GDAL 3.4.1 embarqué par l'image qgis/qgis:release-3_34, vérifié
empiriquement — design §1).

Round-trip jamais invoqué depuis app.pipelines.runtime dans ce chantier :
aucun moteur natif n'a de binding installé ici pour le consommer (design
§1/§2, hors périmètre explicite). Validé uniquement par ses propres tests
unitaires (tests/test_pipeline_exchange.py)."""

import duckdb
import pyarrow

from app.cdc.parquet_writer import write_geoparquet_from_relation
from app.pipelines.runtime import PipelineRuntimeError


def _qi(name: str) -> str:
    # Même duplication délibérée que app.pipelines.runtime._qi/app.cdc.
    # parquet_writer._qi — convention déjà actée dans ce dépôt.
    return '"' + name.replace('"', '""') + '"'


def _geometry_column(relation: duckdb.DuckDBPyRelation, *, fn_label: str) -> str:
    """Détection par TYPE DuckDB (GEOMETRY), jamais par nom de colonne —
    même garantie que app.pipelines.runtime._materialize_reader/
    _materialize_qgis_output. Une seule colonne géométrie attendue (même
    contrat qu'une collection) : en cas de pluralité inattendue, la
    première suffit à ne jamais perdre la géométrie silencieusement."""
    geom_cols = [d[0] for d in relation.description if d[1].id == "geometry"]
    if not geom_cols:
        raise PipelineRuntimeError(f"{fn_label} : la relation ne porte aucune colonne géométrie")
    return geom_cols[0]


def to_arrow_stream(relation: duckdb.DuckDBPyRelation, *, srid: int) -> pyarrow.RecordBatchReader:
    """Chemin 1 (design §3) : zéro-copie, pour un moteur lié in-process
    (binding Python/Rust acceptant l'interface Arrow C Data). Force
    ST_SetCRS sur la colonne géométrie avant .arrow() — sans lui, le CRS
    embarqué dans les métadonnées Arrow de la colonne reste vide ({}),
    vérifié empiriquement (design §1)."""
    geom_col = _geometry_column(relation, fn_label="to_arrow_stream")
    other_cols = [c for c in relation.columns if c != geom_col]
    select_list = ", ".join(
        [_qi(c) for c in other_cols]
        + [f"ST_SetCRS({_qi(geom_col)}, 'EPSG:{srid}') AS {_qi(geom_col)}"]
    )
    return relation.select(select_list).arrow()


def from_arrow_stream(
    conn: duckdb.DuckDBPyConnection, reader: pyarrow.RecordBatchReader, *, view_name: str
) -> None:
    """Symétrique de to_arrow_stream, sans jamais passer par un fichier —
    enregistre le flux Arrow comme TEMP TABLE DuckDB. Un RecordBatchReader
    ne peut être consommé qu'une seule fois : appeler cette fonction deux
    fois avec le même reader échoue ou renvoie une table vide au second
    appel, jamais garanti — aucune garde runtime ici, cohérent avec le fait
    qu'aucun code d'exécution réel n'appelle encore cette fonction dans ce
    chantier (design §4).

    IMPORTANT, vérifié empiriquement (absent du design, trouvé en écrivant
    ce plan) : `conn` doit être une connexion DuckDB DIFFÉRENTE de celle qui
    a produit la relation passée à `to_arrow_stream` pour obtenir `reader`.
    Enregistrer sur une connexion un RecordBatchReader non drainé produit
    par CETTE MÊME connexion, puis exécuter une requête dessus, deadlocke
    `conn.execute()` indéfiniment (pas une erreur, un vrai blocage,
    reproduit sous `timeout`) — DuckDB ne permet pas d'exécuter une
    nouvelle requête sur une connexion tant qu'un flux Arrow issu de cette
    connexion n'a pas été intégralement drainé. Aucune garde runtime
    possible ici : un RecordBatchReader ne permet pas d'introspecter la
    connexion DuckDB qui l'a produit. Dans l'usage visé (design §3, chemin
    1), ce n'est normalement jamais un problème : le binding du futur
    moteur consomme entièrement `reader` avant de renvoyer un NOUVEAU
    RecordBatchReader en sortie, non lié à la connexion source."""
    tmp_name = f"__exchange_arrow_src_{view_name}"
    conn.register(tmp_name, reader)
    try:
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT * FROM {_qi(tmp_name)}")
    finally:
        conn.unregister(tmp_name)


def to_geoparquet_file(relation: duckdb.DuckDBPyRelation, *, srid: int, path: str) -> None:
    """Chemin 2 (design §3) : repli GeoParquet natif DuckDB (writer
    app.cdc.parquet_writer, mesuré 8-10x plus rapide/compact que tout pont
    GDAL, design §1), pour un moteur qui reste un process séparé mais
    comprend Parquet."""
    geom_col = _geometry_column(relation, fn_label="to_geoparquet_file")
    write_geoparquet_from_relation(relation, srid=srid, geometry_column=geom_col, path=path)
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `cd core && uv run pytest tests/test_pipeline_exchange.py -v`
Expected: PASS — 6 tests passent. **Si l'un des deux tests de round-trip Arrow (`test_arrow_round_trip_preserves_schema_crs_and_values`, `test_from_arrow_stream_unregisters_its_internal_arrow_source`) reste bloqué sans jamais rendre la main (pas d'échec, un vrai hang) : interrompre (Ctrl-C), et vérifier qu'aucune des deux n'appelle `to_arrow_stream` et `from_arrow_stream` avec la relation source et la connexion cible issues de la MÊME connexion DuckDB — deadlock réel et déjà rencontré en écrivant ce plan (cf. section "Risque supplémentaire trouvé en vérifiant" plus haut), pas une supposition.**

- [ ] **Step 5: Vérifier qu'aucune régression n'a été introduite sur `app/pipelines/runtime.py`**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py tests/test_pipeline_jobs.py tests/test_pipeline_routes.py -v`
Expected: PASS — `app/pipelines/exchange.py` importe `PipelineRuntimeError` depuis `runtime.py` mais `runtime.py` lui-même n'est pas modifié ; aucune régression attendue.

- [ ] **Step 6: Commit**

```bash
cd core
git add app/pipelines/exchange.py tests/test_pipeline_exchange.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute le module d'échange Arrow/GeoParquet pour futurs moteurs natifs

app.pipelines.exchange (to_arrow_stream/from_arrow_stream/to_geoparquet_file) —
seam posé pour un futur chantier "premier moteur natif", jamais consommé
par runtime.py ici. QGIS explicitement hors périmètre (aucun driver
Parquet/Arrow dans son GDAL embarqué).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `OperationContract.exchange` — champ additif, jamais consommé

**Files:**
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_ops_contracts.py`

**Interfaces:**
- Consumes: rien de nouveau.
- Produces : `OperationContract.exchange: Literal["arrow_stream", "geoparquet_file"] | None` (défaut `None`), lu par aucun code d'exécution dans ce chantier.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter en fin de `core/tests/test_pipeline_ops_contracts.py` :

```python
def test_operation_contract_accepts_explicit_exchange_value():
    contract = OperationContract(
        op="transform.fake-native",
        kind="transform",
        params_schema=TransformFilterParams,
        exchange="arrow_stream",
    )
    assert contract.exchange == "arrow_stream"


def test_all_nineteen_operations_default_exchange_to_none():
    from app.pipelines.ops.contracts import OPERATIONS

    for op, contract in OPERATIONS.items():
        assert contract.exchange is None, op


def test_ops_catalog_never_exposes_the_exchange_field():
    # Garde de régression (design §2 : "exchange n'entre jamais dans
    # ops_catalog()") — passe déjà avant ce champ puisque ops_catalog()
    # construit un dict à 3 clés fixes, mais documente et verrouille la
    # garantie plutôt que de la supposer.
    from app.pipelines.ops.contracts import ops_catalog

    catalog = ops_catalog()
    for op, entry in catalog.items():
        assert set(entry) == {"kind", "paramsSchema", "acceptsSecondaryInput"}, op
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `cd core && uv run pytest tests/test_pipeline_ops_contracts.py -v`
Expected: FAIL sur `test_operation_contract_accepts_explicit_exchange_value` — `TypeError: OperationContract.__init__() got an unexpected keyword argument 'exchange'`. Les deux autres nouveaux tests passent déjà (attendu, cf. commentaire) ; seul l'échec ci-dessus doit être corrigé.

- [ ] **Step 3: Ajouter le champ `exchange`**

Dans `core/app/pipelines/ops/contracts.py`, modifier la classe `OperationContract` :

```python
@dataclass(frozen=True)
class OperationContract:
    op: str
    kind: Literal["reader", "transform", "writer"]
    params_schema: type[BaseModel]
    accepts_secondary_input: bool = False
    engine: str | None = None
    engine_license: str | None = None
    is_copyleft: bool = False
    execution_model: Literal["in_process", "sidecar"] = "in_process"
    # Piège Python latent : un `def` nu donné ici en défaut (au lieu de `None`)
    # deviendrait un attribut de classe et serait lié comme méthode (self/le
    # contrat injecté en premier argument), pas un simple callable — inoffensif
    # aujourd'hui (défauts `None`, chaque entrée du registre passe son
    # callable en argument d'instance, jamais en défaut de classe), mais à
    # garder à l'esprit pour tout futur mainteneur de ce champ.
    compile: Callable[..., str] | None = None
    output_srid: Callable[..., int] | None = None
    # Design docs/superpowers/specs/2026-09-16-ipc-echange-duckdb-arrow-
    # design.md §2 : canal d'échange DuckDB↔futur moteur natif. None pour
    # les 19 op existantes (aucune ne l'utilise) — le champ existe pour
    # qu'un futur chantier "premier moteur natif" l'utilise sans redevoir
    # étendre ce dataclass. Jamais lu par runtime.py dans ce chantier (rien
    # à brancher, aucun moteur ne le consomme encore) ; jamais exposé par
    # ops_catalog() (même traitement que engine/engine_license/
    # execution_model, déjà invisibles côté shell).
    exchange: Literal["arrow_stream", "geoparquet_file"] | None = None

    def __post_init__(self) -> None:
        if self.is_copyleft and self.execution_model != "sidecar":
            raise ValueError(
                f"'{self.op}': moteur copyleft ({self.engine}) exige execution_model='sidecar'"
            )
```

(Seul le champ `exchange` est ajouté, juste après `output_srid` ; `__post_init__` est inchangé.)

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `cd core && uv run pytest tests/test_pipeline_ops_contracts.py -v`
Expected: PASS — tous les tests (existants + les 3 nouveaux) passent.

- [ ] **Step 5: Vérifier l'absence de régression sur le catalogue public**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py tests/test_pipeline_routes.py -v`
Expected: PASS — `test_get_pipelines_ops_returns_all_nineteen` (toujours 19 op, `exchange` non exposé) reste vert sans modification.

- [ ] **Step 6: Commit**

```bash
cd core
git add app/pipelines/ops/contracts.py tests/test_pipeline_ops_contracts.py
git commit -m "$(cat <<'EOF'
feat(core): étend OperationContract d'un champ exchange (arrow_stream/geoparquet_file)

Champ additif, défaut None sur les 19 op existantes, jamais consommé par
runtime.py ni exposé par ops_catalog() dans ce chantier — posé pour le
futur chantier "premier moteur natif" (suite d'OperationContract).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Vérification finale et clôture

**Files:**
- Modify: `CLAUDE.md` (entrée `### Livré`)

**Interfaces:**
- Consumes: résultats réels des étapes précédentes.
- Produces: rien de nouveau côté code.

- [ ] **Step 1: Suite ciblée sur les fichiers touchés/voisins**

Run:
```bash
cd core && uv run pytest tests/test_cdc_parquet_writer.py tests/test_pipeline_exchange.py \
  tests/test_pipeline_ops_contracts.py tests/test_pipeline_ops_schemas.py \
  tests/test_pipeline_routes.py tests/test_pipeline_runtime.py tests/test_pipeline_compiler.py \
  tests/test_pipeline_jobs.py -v
```
Expected: PASS, 0 failed.

- [ ] **Step 2: Qualité statique**

Run:
```bash
cd core
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run mypy app/ || true
uv run lint-imports
```
Expected: tous verts (le `mypy app/ || true` est informationnel comme en CI — signaler ici toute erreur nouvelle sur `app/pipelines/exchange.py`/`app/cdc/parquet_writer.py` même si non bloquante, et la corriger si triviale).

- [ ] **Step 3: Suite complète du cœur**

Suivre `CLAUDE.md` § Commandes (conteneur `postgis-test` réel, `CORE_TEST_DATABASE_URL` positionné, schéma `postgresql+psycopg://`) :
```bash
cd core && uv run pytest
```
Expected: aucune régression attribuable à ce plan. Ce chantier ne touche ni Postgres, ni les migrations, ni RLS — tout échec doit être confirmé préexistant/sans rapport avant clôture (piège CLAUDE.md n°3/n°9 : vérifier `git diff --stat origin/dev...HEAD` sur les fichiers en échec, rejouer en isolation si contention suspectée), jamais supposé.

- [ ] **Step 4: Aucune nouvelle surface publique**

```bash
cd core
grep -n "@router\.\|@app\.\|mcp.tool" app/pipelines/exchange.py app/cdc/parquet_writer.py
```
Expected: aucune sortie (ni route REST, ni outil MCP ajoutés) — confirme qu'aucune entrée `docs/revue/inventaire-fonctionnalites.jsonl` n'est requise et que `feature_health_cli.py --check` n'a rien de nouveau à voir.

- [ ] **Step 5: OpenAPI/types TS — diff vide attendu, à vérifier**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff --stat -- core/openapi.json

cd ../shell && npm run gen:api-types
git diff --stat -- shell/src/api/generated/core-schema.d.ts
```
Expected: les deux diffs sont **vides** (aucune route ni modèle Pydantic exposé n'a changé). Si non vide, investiguer avant de continuer — ne jamais committer un diff inattendu sans comprendre pourquoi.

- [ ] **Step 6: Aucun fichier `shell/` touché**

```bash
git diff --stat origin/dev...HEAD -- shell/
```
Expected: vide (chantier `core-only`, cf. titre du design).

- [ ] **Step 7: Mettre à jour `CLAUDE.md`**

Lire l'entrée `### Livré` existante juste au-dessus (« `OperationContract` — remplace... ») pour le style attendu. Ajouter une nouvelle entrée `### Livré` (même section) titrée quelque chose comme **`IPC d'échange DuckDB↔Arrow`**, résumant, à partir des résultats **réels** des Steps 1 à 6 ci-dessus (pas de chiffres inventés) :
- ce qui a été livré (`app/pipelines/exchange.py`, `write_geoparquet_from_relation`, `OperationContract.exchange`) ;
- la décision prise sur le risque §5 du design (ChangeRow écarté, cf. section "Décision prise en amont" de ce plan) ;
- le compte de suite final (core, ciblé + complet) ;
- confirmation diff OpenAPI/TS vide, confirmation zéro fichier `shell/` touché ;
- tout écart réel trouvé en exécutant (pas seulement au texte de ce plan) qui n'aurait pas été anticipé ci-dessus.

Puis committer :
```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: clôture du chantier IPC d'échange DuckDB↔Arrow

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
