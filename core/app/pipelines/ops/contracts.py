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

from collections.abc import Iterable
from dataclasses import replace
from types import ModuleType

from pydantic import BaseModel

from app.auth.dependency import (
    is_pipeline_experimental_ops_enabled,
    is_pipeline_file_io_enabled,
    is_raster_enabled,
)
from app.pipelines import compiler as _compiler
from app.pipelines import http_call_runtime as _http_call
from app.pipelines.ops import (
    attrs,
    cloudfiles,
    dbio,
    dbio2,
    geom2,
    messaging,
    quality,
    raster2,
    readers2,
    reliquats,
)
from app.pipelines.ops import database as _database
from app.pipelines.ops import execute as _execute
from app.pipelines.ops import filtering as _filtering
from app.pipelines.ops import geocode as _geocode
from app.pipelines.ops import raster as _raster
from app.pipelines.ops import routing as _routing
from app.pipelines.ops import wfs as _wfs
from app.pipelines.ops.operation_contract import OperationContract
from app.pipelines.ops.schemas import (
    ReaderCollectionParams,
    ReaderConnectorBigQueryParams,
    ReaderConnectorBlobParams,
    ReaderConnectorDatabricksParams,
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
    TransformDensifyParams,
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
    TransformHttpCallParams,
    TransformIntersectionParams,
    TransformJoinParams,
    TransformMapSchemaParams,
    TransformMergeChildrenParams,
    TransformMergeParams,
    TransformMinimumBoundingCircleParams,
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
    TransformTriangulateParams,
    TransformValidateAttributesParams,
    WriterCollectionParams,
    WriterDatasetParams,
    WriterExportParams,
    WriterFileParams,
)

# Registre « socle » (ops livrées avant la fermeture FME 2026-10-15) : figé, les nouvelles
# ops vivent dans un module de voie (cf. LANE_MODULES ci-dessous), jamais ici.
_BASE_OPERATIONS: dict[str, OperationContract] = {
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
        needs_columns=True,
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
        needs_columns=True,
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
    "reader.connector.databricks": OperationContract(
        op="reader.connector.databricks",
        kind="reader",
        params_schema=ReaderConnectorDatabricksParams,
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
    "transform.triangulate": OperationContract(
        op="transform.triangulate",
        kind="transform",
        params_schema=TransformTriangulateParams,
        engine="shapely",
        engine_license="BSD-3-Clause (Shapely)",
        execute=_execute._execute_triangulate,
    ),
    "transform.densify": OperationContract(
        op="transform.densify",
        kind="transform",
        params_schema=TransformDensifyParams,
        engine="shapely",
        engine_license="BSD-3-Clause (Shapely)",
        execute=_execute._execute_densify,
    ),
    "transform.minimumBoundingCircle": OperationContract(
        op="transform.minimumBoundingCircle",
        kind="transform",
        params_schema=TransformMinimumBoundingCircleParams,
        engine="shapely",
        engine_license="BSD-3-Clause (Shapely)",
        execute=_execute._execute_minimum_bounding_circle,
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
    # Voie M (ARC vague 4) : params définis dans le module de chaque op (fichiers neufs).
    "transform.geocode": OperationContract(
        op="transform.geocode",
        kind="transform",
        params_schema=_geocode.TransformGeocodeParams,
        engine="python",
        engine_license="Apache-2.0 (httpx) ; BAN/Géoplateforme (Etalab 2.0) ou Nominatim (ODbL)",
        execute=_geocode.execute_geocode,
        needs_runtime_context=True,
        output_srid=_geocode._output_srid,
    ),
    # Voie P (ARC-34, ADR 0025) : routage Valhalla, params dans ops/routing.py (fichier neuf).
    "transform.isochrone": OperationContract(
        op="transform.isochrone",
        kind="transform",
        params_schema=_routing.TransformIsochroneParams,
        engine="python",
        engine_license="MIT (Valhalla, service externe) ; données OSM (ODbL) de l'opérateur",
        execute=_routing.execute_isochrone,
        needs_runtime_context=True,
        output_srid=_routing._output_srid,
    ),
    "transform.route": OperationContract(
        op="transform.route",
        kind="transform",
        params_schema=_routing.TransformRouteParams,
        engine="python",
        engine_license="MIT (Valhalla, service externe) ; données OSM (ODbL) de l'opérateur",
        execute=_routing.execute_route,
        needs_runtime_context=True,
        output_srid=_routing._output_srid,
    ),
    "reader.wfs": OperationContract(
        op="reader.wfs",
        kind="reader",
        params_schema=_wfs.ReaderWfsParams,
    ),
    "reader.raster": OperationContract(
        op="reader.raster",
        kind="reader",
        params_schema=_raster.ReaderRasterParams,
        enabled_when=is_raster_enabled,
    ),
    "transform.zonalStats": OperationContract(
        op="transform.zonalStats",
        kind="transform",
        params_schema=_raster.TransformZonalStatsParams,
        engine="python",
        engine_license="BSD-3-Clause (rasterio) ; GDAL (MIT)",
        execute=_raster.execute_zonal_stats,
        needs_runtime_context=True,
        enabled_when=is_raster_enabled,
    ),
    "transform.testFilter": OperationContract(
        op="transform.testFilter",
        kind="transform",
        params_schema=_filtering.TransformTestFilterParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        execute=_filtering.execute_test_filter,
    ),
    "transform.sampler": OperationContract(
        op="transform.sampler",
        kind="transform",
        params_schema=_filtering.TransformSamplerParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_filtering.compile_sampler,
    ),
    "transform.neighborFinder": OperationContract(
        op="transform.neighborFinder",
        kind="transform",
        params_schema=_filtering.TransformNeighborFinderParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_filtering.compile_neighbor_finder,
        pre_check=_filtering.pre_check_neighbor_finder,
    ),
    "transform.sqlExecutor": OperationContract(
        op="transform.sqlExecutor",
        kind="transform",
        params_schema=_database.TransformSqlExecutorParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        execute=_database.execute_sql_executor,
    ),
    "transform.httpCall": OperationContract(
        op="transform.httpCall",
        kind="transform",
        params_schema=TransformHttpCallParams,
        engine="python",
        engine_license="Apache-2.0 (requests) + Apache-2.0 (dlt, pagination)",
        execute=_http_call.execute_http_call,
        needs_runtime_context=True,
    ),
}

# Couture anti-conflit (plan docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md
# §1.2) : chaque voie déclare ses ops dans son propre module (`CONTRACTS`, + `READERS`/
# `WRITERS` agrégés par app.pipelines.registries) ; ce tuple est la seule ligne partagée.
# Un module de voie n'importe JAMAIS ce module (ni runtime/registries) au niveau module :
# cycle d'import — OperationContract vient de ops/operation_contract.py.
LANE_MODULES: tuple[ModuleType, ...] = (
    attrs,
    dbio,
    geom2,
    cloudfiles,
    messaging,
    raster2,
    readers2,
    dbio2,
    reliquats,
    quality,
)


def _aggregate(
    base: dict[str, OperationContract], lanes: tuple[ModuleType, ...]
) -> dict[str, OperationContract]:
    operations = dict(base)
    for lane in lanes:
        for contract in lane.CONTRACTS:
            if contract.op in operations:
                raise ValueError(f"op '{contract.op}' déclarée deux fois ({lane.__name__})")
            operations[contract.op] = contract
    return operations


# Op « expérimentales » (lot 9, release v0.2.0) : parlent à un service tiers (messagerie,
# cloud, bases externes, OGC, routage, géocodage…) et n'ont été testées que contre des
# doubles, jamais contre le vrai service. Critère et preuve par op :
# docs/revue/2026-10-16-ops-experimentales.md. Hors CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED
# elles sont masquées du catalogue et refusées à l'écriture et à l'exécution.
EXPERIMENTAL_OPS: frozenset[str] = frozenset(
    {
        # messagerie et notifications (doubles uniquement)
        "writer.email",
        "writer.slack",
        "writer.trello",
        "writer.servicebus",
        "writer.azurequeue",
        "reader.azurequeue",
        "writer.sns",
        "writer.kinesis",
        "reader.kinesis",
        "writer.rabbitmq",
        "transform.mcpCall",
        # fichiers cloud / portails / FTP
        "reader.cloudfile",
        "reader.ckan",
        "reader.arcgisonline",
        "reader.ftp",
        "writer.ftp",
        "reader.connector.googlesheets",
        # entrepôts et bases externes
        "reader.connector.snowflake",
        "reader.connector.bigquery",
        "reader.connector.mssql",
        "reader.connector.oracle",
        "reader.connector.databricks",
        "reader.connector.blob",
        "reader.mongodb",
        # services géospatiaux tiers (OGC, STAC, tuiles, routage, géocodage)
        "reader.wms",
        "reader.wcs",
        "reader.wfs",
        "transform.imageFetch",
        "transform.webMapTiler",
        "transform.geocode",
        "transform.isochrone",
        "transform.route",
    }
)


def _flag_experimental(operations: dict[str, OperationContract]) -> dict[str, OperationContract]:
    unknown = EXPERIMENTAL_OPS - operations.keys()
    if unknown:
        raise ValueError(f"EXPERIMENTAL_OPS référence des op inconnues : {sorted(unknown)}")
    return {
        op: replace(c, experimental=True) if op in EXPERIMENTAL_OPS else c
        for op, c in operations.items()
    }


OPERATIONS: dict[str, OperationContract] = _flag_experimental(
    _aggregate(_BASE_OPERATIONS, LANE_MODULES)
)
# Ops apportées par les modules de voie : les tests à liste figée comparent
# `set(...) - LANE_OPS` à la liste socle, chaque voie teste ses ops dans son propre fichier.
LANE_OPS: frozenset[str] = frozenset(OPERATIONS) - frozenset(_BASE_OPERATIONS)

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
    sa clé `description` — pour plusieurs op (les connecteurs +
    transform.merge), ce docstring contient du jargon développeur (noms de
    classes, chemins de module, renvois "design §n"/"SPnn") qui n'a rien à
    faire dans le tooltip de palette lu par
    shell/src/builder/pipeline/PipelinePalette.tsx. Le docstring de classe
    reste une documentation développeur complète (paragraphes suivants) ;
    seul le premier paragraphe — rédigé pour être compris par l'auteur d'un
    pipeline — atteint le catalogue exposé par GET /pipelines/ops."""
    return description.split("\n\n", 1)[0].strip()


def blocked_experimental_ops(ops: Iterable[str]) -> list[str]:
    """Op expérimentales parmi `ops`, triées, quand le flag est éteint (sinon [])."""
    if is_pipeline_experimental_ops_enabled():
        return []
    return sorted({op for op in ops if op in EXPERIMENTAL_OPS})


def experimental_refusal(blocked: list[str]) -> str:
    return (
        f"Opération expérimentale désactivée : {', '.join(blocked)}. Elle n'a jamais été "
        "rejouée contre le service réel ; un administrateur peut l'activer avec "
        "CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED=true."
    )


def ops_catalog() -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for op, model in OP_PARAMS.items():
        contract = OPERATIONS[op]
        if contract.enabled_when is not None and not contract.enabled_when():
            continue
        if contract.experimental and not is_pipeline_experimental_ops_enabled():
            continue
        schema = model.model_json_schema()
        if schema.get("description"):
            schema["description"] = _user_facing_description(schema["description"])
        catalog[op] = {
            "kind": OP_KINDS[op],
            "paramsSchema": schema,
            "acceptsSecondaryInput": op in BINARY_OPS,
            "experimental": contract.experimental,
        }
    return catalog
