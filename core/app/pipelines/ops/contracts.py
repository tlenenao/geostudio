# SPDX-License-Identifier: Apache-2.0
"""Contrat unique par op de pipeline (schéma/moteur/licence/modèle
d'exécution/compilateur/règle de SRID de sortie) — design
docs/superpowers/specs/2026-09-16-operation-contract-design.md.

Remplace, pour les 19 op de pipeline déjà livrées, les 5 structures
parallèles indexées par nom d'op qui existaient jusqu'ici
(app.pipelines.ops.schemas::OP_PARAMS/OP_KINDS/BINARY_OPS,
app.pipelines.compiler::compile_transform_sql/transform_output_srid) : le
registre OPERATIONS (construit ci-dessous) devient la seule source, ces
structures en deviennent des vues dérivées, définies dans CE module (pas
dans ops/schemas.py — un import circulaire réel l'interdit, cf. Écarts au
texte de la spec du plan).

Règle non négociable, vérifiée à la CONSTRUCTION de chaque contrat (donc à
chaque import de ce module, pas seulement par un test dédié) :
généralisation de la décision SP-15d déjà en vigueur pour QGIS — un moteur
copyleft (is_copyleft=True) exige un modèle d'exécution sidecar, jamais de
bindings in-process."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.auth.dependency import is_pipeline_file_io_enabled
from app.pipelines import compiler as _compiler
from app.pipelines.ops.schemas import (
    ReaderCollectionParams,
    ReaderConnectorBigQueryParams,
    ReaderConnectorBlobParams,
    ReaderConnectorMssqlParams,
    ReaderConnectorOracleParams,
    ReaderConnectorPostgresParams,
    ReaderConnectorRestParams,
    ReaderConnectorSnowflakeParams,
    ReaderFileParams,
    TransformAggregateParams,
    TransformBoundingGeometryParams,
    TransformBufferParams,
    TransformBulkRemoveAttributesParams,
    TransformBulkRenameAttributesParams,
    TransformCentroidParams,
    TransformConcatCoordinatesParams,
    TransformConvexHullParams,
    TransformCountVerticesParams,
    TransformCountWithinParams,
    TransformCreateGeometryParams,
    TransformDeriveParams,
    TransformDetectChangesParams,
    TransformExplodeGeometryParams,
    TransformExplodeListParams,
    TransformExposeAttributesParams,
    TransformExtractCoordinatesParams,
    TransformExtractDimensionParams,
    TransformExtractElevationParams,
    TransformExtractSridParams,
    TransformFilterParams,
    TransformFormatCoordinatesParams,
    TransformH3AggregateParams,
    TransformIntersectionParams,
    TransformJoinParams,
    TransformMapSchemaParams,
    TransformMergeChildrenParams,
    TransformMergeParams,
    TransformQgisParams,
    TransformReprojectAttributeParams,
    TransformReprojectParams,
    TransformResolveOverlapsParams,
    TransformRotateGeometryParams,
    TransformRoundCoordinatesParams,
    TransformScaleGeometryParams,
    TransformScanSchemaParams,
    TransformSelectParams,
    TransformSetSridParams,
    TransformSimplifyParams,
    TransformSnapToLayerParams,
    TransformSortParams,
    TransformSwapCoordinatesParams,
    TransformTranslateGeometryParams,
    TransformValidateAttributesParams,
    WriterCollectionParams,
    WriterDatasetParams,
    WriterExportParams,
    WriterFileParams,
)


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
    # Vague 2 (design docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md
    # §3.1) : quand True, compile_transform_sql résout input_columns/join_columns via un
    # DESCRIBE (app.pipelines.runtime) avant d'appeler `compile` — extension chirurgicale,
    # jamais de connexion DuckDB dans ce module lui-même.
    needs_columns: bool = False
    # Design docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md §7.2 :
    # mutuellement exclusif avec `compile` — un op "transform" a l'un ou l'autre, jamais les
    # deux, jamais aucun des deux. Signature : (conn, *, input_view, view_name, params) -> None,
    # matérialise `view_name` lui-même (contrairement à `compile`, qui retourne une simple
    # chaîne SQL exécutée par l'appelant).
    execute: Callable[..., None] | None = None
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
    # Design docs/superpowers/specs/2026-09-17-desktop-etl-standalone-design.md
    # §3 : capacité instance-wide optionnelle (même patron que
    # is_etl_enabled) qui gate la VISIBILITÉ de l'op dans ops_catalog() —
    # PAS le garde-fou de sécurité réel, qui vit au point d'exécution
    # (app.pipelines.runtime, jamais ici) : ce champ ne remplace aucune
    # vérification, il évite seulement de proposer une op inutilisable dans
    # la palette de l'éditeur.
    enabled_when: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        if self.is_copyleft and self.execution_model != "sidecar":
            raise ValueError(
                f"'{self.op}': moteur copyleft ({self.engine}) exige execution_model='sidecar'"
            )


OPERATIONS: dict[str, OperationContract] = {
    "reader.collection": OperationContract(
        op="reader.collection",
        kind="reader",
        params_schema=ReaderCollectionParams,
    ),
    "transform.filter": OperationContract(
        op="transform.filter",
        kind="transform",
        params_schema=TransformFilterParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_filter,
    ),
    "transform.select": OperationContract(
        op="transform.select",
        kind="transform",
        params_schema=TransformSelectParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_select,
    ),
    "transform.derive": OperationContract(
        op="transform.derive",
        kind="transform",
        params_schema=TransformDeriveParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_derive,
    ),
    "transform.aggregate": OperationContract(
        op="transform.aggregate",
        kind="transform",
        params_schema=TransformAggregateParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_aggregate,
    ),
    "transform.join": OperationContract(
        op="transform.join",
        kind="transform",
        params_schema=TransformJoinParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_join,
    ),
    "transform.buffer": OperationContract(
        op="transform.buffer",
        kind="transform",
        params_schema=TransformBufferParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_buffer,
    ),
    "transform.reproject": OperationContract(
        op="transform.reproject",
        kind="transform",
        params_schema=TransformReprojectParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_reproject,
        output_srid=_compiler._output_srid_reproject,
    ),
    "transform.intersection": OperationContract(
        op="transform.intersection",
        kind="transform",
        params_schema=TransformIntersectionParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_intersection,
        output_srid=_compiler._output_srid_reconcile_join,
    ),
    "transform.countWithin": OperationContract(
        op="transform.countWithin",
        kind="transform",
        params_schema=TransformCountWithinParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_count_within,
        output_srid=_compiler._output_srid_reconcile_join,
    ),
    "transform.h3Aggregate": OperationContract(
        op="transform.h3Aggregate",
        kind="transform",
        params_schema=TransformH3AggregateParams,
        engine="duckdb",
        engine_license="MIT (DuckDB) + Apache-2.0 (extension communautaire h3)",
        compile=_compiler._compile_h3_aggregate,
        output_srid=_compiler._output_srid_h3_aggregate,
    ),
    "transform.qgis": OperationContract(
        op="transform.qgis",
        kind="transform",
        params_schema=TransformQgisParams,
        engine="qgis",
        engine_license="GPL-2.0-or-later (QGIS)",
        is_copyleft=True,
        execution_model="sidecar",
        output_srid=_compiler._output_srid_qgis,
    ),
    "transform.bulkRemoveAttributes": OperationContract(
        op="transform.bulkRemoveAttributes",
        kind="transform",
        params_schema=TransformBulkRemoveAttributesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_bulk_remove_attributes,
    ),
    "transform.bulkRenameAttributes": OperationContract(
        op="transform.bulkRenameAttributes",
        kind="transform",
        params_schema=TransformBulkRenameAttributesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_bulk_rename_attributes,
    ),
    "transform.scanSchema": OperationContract(
        op="transform.scanSchema",
        kind="transform",
        params_schema=TransformScanSchemaParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_scan_schema,
    ),
    "writer.collection": OperationContract(
        op="writer.collection",
        kind="writer",
        params_schema=WriterCollectionParams,
    ),
    "writer.export": OperationContract(
        op="writer.export",
        kind="writer",
        params_schema=WriterExportParams,
    ),
    "writer.dataset": OperationContract(
        op="writer.dataset",
        kind="writer",
        params_schema=WriterDatasetParams,
    ),
    "reader.connector.rest": OperationContract(
        op="reader.connector.rest",
        kind="reader",
        params_schema=ReaderConnectorRestParams,
    ),
    "reader.connector.postgres": OperationContract(
        op="reader.connector.postgres",
        kind="reader",
        params_schema=ReaderConnectorPostgresParams,
    ),
    "reader.connector.snowflake": OperationContract(
        op="reader.connector.snowflake",
        kind="reader",
        params_schema=ReaderConnectorSnowflakeParams,
    ),
    "reader.connector.bigquery": OperationContract(
        op="reader.connector.bigquery",
        kind="reader",
        params_schema=ReaderConnectorBigQueryParams,
    ),
    "reader.connector.mssql": OperationContract(
        op="reader.connector.mssql",
        kind="reader",
        params_schema=ReaderConnectorMssqlParams,
    ),
    "reader.connector.oracle": OperationContract(
        op="reader.connector.oracle",
        kind="reader",
        params_schema=ReaderConnectorOracleParams,
    ),
    "reader.connector.blob": OperationContract(
        op="reader.connector.blob",
        kind="reader",
        params_schema=ReaderConnectorBlobParams,
        # Écart au brief de Task 15 (même écart, même rationale que Task
        # 12/13/14) : aucun des 6 autres readers déjà livrés
        # (rest/postgres/snowflake/bigquery/mssql/oracle) ne pose
        # `engine`/`engine_license` sur son OperationContract — ces deux
        # champs ne sont utilisés que par les transforms DuckDB dans ce
        # registre (vérifié par grep sur ce module, aucune autre occurrence
        # de `engine_license` dans app.pipelines). Rester cohérent avec les 6
        # lecteurs existants plutôt qu'introduire une exception isolée.
    ),
    "transform.merge": OperationContract(
        op="transform.merge",
        kind="transform",
        params_schema=TransformMergeParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_merge,
        output_srid=_compiler._output_srid_reconcile_join,
    ),
    "transform.scaleGeometry": OperationContract(
        op="transform.scaleGeometry",
        kind="transform",
        params_schema=TransformScaleGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_scale_geometry,
    ),
    "transform.swapCoordinates": OperationContract(
        op="transform.swapCoordinates",
        kind="transform",
        params_schema=TransformSwapCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_swap_coordinates,
    ),
    "transform.translateGeometry": OperationContract(
        op="transform.translateGeometry",
        kind="transform",
        params_schema=TransformTranslateGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_translate_geometry,
    ),
    "transform.rotateGeometry": OperationContract(
        op="transform.rotateGeometry",
        kind="transform",
        params_schema=TransformRotateGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_rotate_geometry,
    ),
    "transform.createGeometry": OperationContract(
        op="transform.createGeometry",
        kind="transform",
        params_schema=TransformCreateGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_create_geometry,
    ),
    "transform.roundCoordinates": OperationContract(
        op="transform.roundCoordinates",
        kind="transform",
        params_schema=TransformRoundCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_round_coordinates,
    ),
    "transform.concatCoordinates": OperationContract(
        op="transform.concatCoordinates",
        kind="transform",
        params_schema=TransformConcatCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_concat_coordinates,
    ),
    "transform.extractCoordinates": OperationContract(
        op="transform.extractCoordinates",
        kind="transform",
        params_schema=TransformExtractCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_extract_coordinates,
    ),
    "transform.extractElevation": OperationContract(
        op="transform.extractElevation",
        kind="transform",
        params_schema=TransformExtractElevationParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_extract_elevation,
    ),
    "transform.extractDimension": OperationContract(
        op="transform.extractDimension",
        kind="transform",
        params_schema=TransformExtractDimensionParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_extract_dimension,
    ),
    "transform.countVertices": OperationContract(
        op="transform.countVertices",
        kind="transform",
        params_schema=TransformCountVerticesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_count_vertices,
    ),
    "transform.extractSrid": OperationContract(
        op="transform.extractSrid",
        kind="transform",
        params_schema=TransformExtractSridParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_extract_srid,
    ),
    "transform.setSrid": OperationContract(
        op="transform.setSrid",
        kind="transform",
        params_schema=TransformSetSridParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_set_srid,
        output_srid=_compiler._output_srid_set_srid,
    ),
    "transform.reprojectAttribute": OperationContract(
        op="transform.reprojectAttribute",
        kind="transform",
        params_schema=TransformReprojectAttributeParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_reproject_attribute,
    ),
    "transform.formatCoordinates": OperationContract(
        op="transform.formatCoordinates",
        kind="transform",
        params_schema=TransformFormatCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_format_coordinates,
    ),
    "transform.explodeList": OperationContract(
        op="transform.explodeList",
        kind="transform",
        params_schema=TransformExplodeListParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_explode_list,
    ),
    "transform.explodeGeometry": OperationContract(
        op="transform.explodeGeometry",
        kind="transform",
        params_schema=TransformExplodeGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_explode_geometry,
    ),
    "transform.centroid": OperationContract(
        op="transform.centroid",
        kind="transform",
        params_schema=TransformCentroidParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_centroid,
    ),
    "transform.convexHull": OperationContract(
        op="transform.convexHull",
        kind="transform",
        params_schema=TransformConvexHullParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_convex_hull,
    ),
    "transform.simplify": OperationContract(
        op="transform.simplify",
        kind="transform",
        params_schema=TransformSimplifyParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_simplify,
    ),
    "transform.boundingGeometry": OperationContract(
        op="transform.boundingGeometry",
        kind="transform",
        params_schema=TransformBoundingGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_bounding_geometry,
    ),
    "transform.exposeAttributes": OperationContract(
        op="transform.exposeAttributes",
        kind="transform",
        params_schema=TransformExposeAttributesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_expose_attributes,
    ),
    "transform.validateAttributes": OperationContract(
        op="transform.validateAttributes",
        kind="transform",
        params_schema=TransformValidateAttributesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_validate_attributes,
    ),
    "transform.sort": OperationContract(
        op="transform.sort",
        kind="transform",
        params_schema=TransformSortParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_sort,
    ),
    "transform.detectChanges": OperationContract(
        op="transform.detectChanges",
        kind="transform",
        params_schema=TransformDetectChangesParams,
        accepts_secondary_input=True,
        needs_columns=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_detect_changes,
    ),
    "transform.mergeChildren": OperationContract(
        op="transform.mergeChildren",
        kind="transform",
        params_schema=TransformMergeChildrenParams,
        accepts_secondary_input=True,
        needs_columns=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_merge_children,
    ),
    "transform.mapSchema": OperationContract(
        op="transform.mapSchema",
        kind="transform",
        params_schema=TransformMapSchemaParams,
        needs_columns=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_map_schema,
    ),
    "transform.snapToLayer": OperationContract(
        op="transform.snapToLayer",
        kind="transform",
        params_schema=TransformSnapToLayerParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_snap_to_layer,
        output_srid=_compiler._output_srid_reconcile_join,
    ),
    "transform.resolveOverlaps": OperationContract(
        op="transform.resolveOverlaps",
        kind="transform",
        params_schema=TransformResolveOverlapsParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_resolve_overlaps,
    ),
    "reader.file": OperationContract(
        op="reader.file",
        kind="reader",
        params_schema=ReaderFileParams,
        enabled_when=is_pipeline_file_io_enabled,
    ),
    "writer.file": OperationContract(
        op="writer.file",
        kind="writer",
        params_schema=WriterFileParams,
        enabled_when=is_pipeline_file_io_enabled,
    ),
}

OP_KINDS: dict[str, str] = {op: c.kind for op, c in OPERATIONS.items()}
OP_PARAMS: dict[str, type[BaseModel]] = {op: c.params_schema for op, c in OPERATIONS.items()}

# Op dont la seconde entrée peut venir soit d'un paramètre `withCollectionId`,
# soit d'une arête `role="secondary"` (design SP-15g §2.2/§4.2). Exporté
# (pas `_`-préfixé) : importé directement par app.pipelines.config_validation,
# même package app.pipelines, aucune frontière de couches à traverser.
BINARY_OPS: set[str] = {op for op, c in OPERATIONS.items() if c.accepts_secondary_input}


def parse_op_params(op: str, params: dict) -> BaseModel:
    model = OP_PARAMS.get(op)
    if model is None:
        raise ValueError(f"unknown op '{op}'")
    return model.model_validate(params)


def _user_facing_description(description: str) -> str:
    """N'expose que le premier paragraphe d'un docstring de classe (avant le
    premier saut de ligne vide) comme description utilisateur du catalogue.

    Correctif revue finale GAP-16 (Important I2) : `model_json_schema()`
    reprend tel quel le docstring Python complet d'une classe de params dans
    sa clé `description` — pour 5 op (les connecteurs + transform.qgis/
    transform.merge), ce docstring contient du jargon développeur (noms de
    classes, chemins de module, renvois "design §n"/"SPnn") qui n'a rien à
    faire dans le tooltip de palette lu par
    shell/src/builder/pipeline/PipelinePalette.tsx. Le docstring de classe
    reste une documentation développeur complète (paragraphes suivants) ;
    seul le premier paragraphe — rédigé pour être compris par l'auteur d'un
    pipeline — atteint le catalogue exposé par GET /pipelines/ops."""
    return description.split("\n\n", 1)[0].strip()


def ops_catalog() -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for op, model in OP_PARAMS.items():
        contract = OPERATIONS[op]
        if contract.enabled_when is not None and not contract.enabled_when():
            continue
        schema = model.model_json_schema()
        if schema.get("description"):
            schema["description"] = _user_facing_description(schema["description"])
        catalog[op] = {
            "kind": OP_KINDS[op],
            "paramsSchema": schema,
            "acceptsSecondaryInput": op in BINARY_OPS,
        }
    return catalog
