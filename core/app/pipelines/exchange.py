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
from app.sql_ident import quote_ident_duckdb as _qi


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
