# SPDX-License-Identifier: Apache-2.0
"""Exécution d'un Pipeline (SP-15a) — étage 1 uniquement (DuckDB
in-process), nœud par nœud, sans fusion (design §1 non-but, mitigation D4
de l'étude de faisabilité). Réutilise tel quel : la connexion DuckDB
éphémère (app.analytics.duckdb_conn), le CTE de dédoublonnage GeoParquet
CDC (app.analytics.aggregate._dedup_cte), le chemin d'écriture OGC
Features (insert_feature/rls_scope/validate_feature).

Deux passes, dans cet ordre (comme app.analytics.sql_sandbox._materialize
puis _lock_down — jamais l'inverse) :
  1. matérialiser TOUTES les lectures externes (chaque reader.collection +
     le withCollectionId de chaque transform.join) en TEMP TABLE — pas TEMP
     VIEW, qui resterait paresseuse et referait un accès disque après le
     verrouillage (bug constaté à l'exécution, corrigé en Task 8) ;
  2. verrouiller l'accès externe (enable_external_access=false,
     lock_configuration=true), PUIS exécuter transforms/writers dans
     l'ordre topologique — les expr bornées (filter/derive/aggregate
     metrics) sont validées juste avant d'être compilées (Task 6), jamais
     avant (design Global Constraints : la validation sémantique est une
     affaire d'exécution, pas de sauvegarde).

Convention de colonne géométrie : chaque vue de reader matérialisée
renomme sa colonne géométrie source en "geometry" (quel que soit son nom
réel dans la collection), pour que le reste de la chaîne (writer.collection
compris) n'ait jamais à connaître le nom d'origine — cf. Task 8 note."""
import csv
import io
import json

import duckdb
from sqlalchemy.orm import Session

from app.analytics.aggregate import _dedup_cte, _has_any_file
from app.analytics.duckdb_conn import open_connection
from app.collections import repository as collections_repo
from app.collections.introspection import TableInfo, TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.configs.schemas import PipelineNode, PipelinePayload
from app.features.repository import insert_feature
from app.features.rls import rls_scope
from app.features.validation import validate_feature
from app.pipelines import compiler
from app.pipelines.expr_validation import validate_bounded_expr
from app.pipelines.ops.schemas import (
    ReaderCollectionParams, TransformAggregateParams, TransformDeriveParams,
    TransformFilterParams, TransformJoinParams, WriterCollectionParams, WriterExportParams,
)
from app.sharing.authorization import can
from app.users.models import User


def _qi(name: str) -> str:
    # Duplication délibérée du helper de 2 lignes de app.pipelines.compiler
    # (lui-même une duplication de app.analytics.aggregate._qi) plutôt qu'un
    # import inter-module d'un nom privé `_`-préfixé — cf. compiler.py.
    return '"' + name.replace('"', '""') + '"'


class PipelineRuntimeError(Exception):
    """Erreur d'exécution : la tâche procrastinate (Task 9) l'attrape et
    marque le run 'failed', jamais 'zombie'."""


class NodeStat:
    def __init__(self, node_id: str, op: str, row_count: int | None = None):
        self.nodeId = node_id
        self.op = op
        self.rowCount = row_count

    def to_dict(self) -> dict:
        return {"nodeId": self.nodeId, "op": self.op, "rowCount": self.rowCount}


def _require_readable_collection_id(
    session: Session, *, tenant_id: str, user: User, collection_id: str,
) -> str:
    collection = collections_repo.get_collection(
        session, tenant_id=tenant_id, collection_id=collection_id,
    )
    if collection is None:
        raise PipelineRuntimeError(f"collection '{collection_id}' not found")
    if not can(session, user_id=user.id, action="read",
               item=collections_repo.get_access_facts(collection), kind="collection",
               actor_is_admin=user.is_admin):
        raise PipelineRuntimeError(f"collection '{collection_id}' not found")
    return collection.table_name


def _require_writable_collection(session: Session, *, tenant_id: str, user: User, collection_id: str):
    collection = collections_repo.get_collection(
        session, tenant_id=tenant_id, collection_id=collection_id,
    )
    if collection is None:
        raise PipelineRuntimeError(f"collection '{collection_id}' not found")
    if not can(session, user_id=user.id, action="write",
               item=collections_repo.get_access_facts(collection), kind="collection",
               actor_is_admin=user.is_admin):
        raise PipelineRuntimeError(f"collection '{collection_id}' is not writable")
    if not collection.editable:
        raise PipelineRuntimeError(f"collection '{collection_id}' is not writable")
    return collection


def _table_info_for_collection(session: Session, collection_id: str) -> TableInfo:
    try:
        return introspect_table(session, collection_id)
    except TableNotFound as exc:
        raise PipelineRuntimeError(f"backing table for '{collection_id}' not found") from exc
    except UnsupportedTable as exc:
        raise PipelineRuntimeError(exc.reason) from exc


def _materialize_reader(conn, *, view_name: str, base_uri: str, tenant_id: str, collection_id: str, table_info: TableInfo) -> None:
    # Comme app.analytics.sql_sandbox._materialize : DuckDB ne peut pas
    # déduire un schéma d'un glob qui ne correspond à aucun fichier, donc pas
    # de "vue vide typée" possible ici — échec propre et explicite plutôt
    # qu'une vue dont le schéma serait un mensonge (même choix que
    # sql_sandbox, qui lève SqlSandboxError dans exactement ce cas).
    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        raise PipelineRuntimeError(f"collection '{collection_id}' has no data yet")
    geom_col = table_info.geometry_column
    # Liste explicite (pk + colonnes déclarées + géométrie renommée), jamais
    # "SELECT *" : "live" porte aussi les colonnes de plomberie du CDC
    # (_op/_lsn/_ts, cf. app.analytics.aggregate._dedup_cte) et celles du
    # hive-partitioning du chemin GeoParquet (tenant_id=/collection_id=/dt=,
    # exposées par read_parquet(hive_partitioning=true)) — jamais de vraies
    # données, elles doivent s'arrêter ici plutôt que fuiter jusqu'au writer
    # (où elles feraient échouer validate_feature en "propriété inconnue").
    reserved = {table_info.pk_column, "tenant_id", geom_col}
    prop_cols = [c.name for c in table_info.columns if c.name not in reserved]
    select_parts = [_qi(table_info.pk_column)] + [_qi(c) for c in prop_cols]
    if geom_col:
        select_parts.append(f"{_qi(geom_col)} AS geometry")
    select_list = ", ".join(select_parts)
    cte = _dedup_cte(table_info, base_uri, tenant_id, collection_id)
    # TABLE, pas VIEW : comme app.analytics.sql_sandbox._materialize, il faut
    # matérialiser EAGERLY avant _lock_down — une VIEW resterait paresseuse et
    # ré-exécuterait read_parquet() (donc un accès disque) à chaque requête
    # ultérieure, ce qui échoue une fois enable_external_access=false posé.
    conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS {cte} SELECT {select_list} FROM live")


def _lock_down(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")


def _validate_node_exprs(conn: duckdb.DuckDBPyConnection, node: PipelineNode) -> None:
    if node.op == "transform.filter":
        p = TransformFilterParams.model_validate(node.params)
        validate_bounded_expr(conn, p.expr)
    elif node.op == "transform.derive":
        p = TransformDeriveParams.model_validate(node.params)
        validate_bounded_expr(conn, p.expr)
    elif node.op == "transform.aggregate":
        p = TransformAggregateParams.model_validate(node.params)
        for metric_expr in p.metrics.values():
            validate_bounded_expr(conn, metric_expr)


def _prepare(
    conn, session: Session, payload: PipelinePayload, *, tenant_id: str, user: User, base_uri: str,
) -> tuple[list[PipelineNode], dict[str, str]]:
    """Passe 1 : matérialise tous les readers (+ le withCollectionId de
    chaque transform.join), puis verrouille. Retourne (ordre topologique,
    view_name par node.id) — writer nodes n'ont pas encore de vue."""
    ordered = compiler.topological_order(payload.nodes, payload.edges)
    view_by_node: dict[str, str] = {}

    for node in ordered:
        if node.kind != "reader":
            continue
        p = ReaderCollectionParams.model_validate(node.params)
        table_name = _require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=p.collectionId,
        )
        table_info = _table_info_for_collection(session, table_name)
        view_name = f"node_{node.id}"
        _materialize_reader(
            conn, view_name=view_name, base_uri=base_uri, tenant_id=tenant_id,
            collection_id=p.collectionId, table_info=table_info,
        )
        view_by_node[node.id] = view_name

    for node in ordered:
        if node.op != "transform.join":
            continue
        p = TransformJoinParams.model_validate(node.params)
        table_name = _require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=p.withCollectionId,
        )
        table_info = _table_info_for_collection(session, table_name)
        join_view = f"node_{node.id}__join"
        _materialize_reader(
            conn, view_name=join_view, base_uri=base_uri, tenant_id=tenant_id,
            collection_id=p.withCollectionId, table_info=table_info,
        )

    _lock_down(conn)
    return ordered, view_by_node


def _execute_transform_chain(
    conn, ordered: list[PipelineNode], edges, view_by_node: dict[str, str], *, stop_at: str | None = None,
) -> list["NodeStat"]:
    stats: list[NodeStat] = []
    for node in ordered:
        if node.kind == "reader":
            stats.append(NodeStat(node.id, node.op, _view_row_count(conn, view_by_node[node.id])))
            if stop_at == node.id:
                return stats
            continue
        if node.kind != "transform":
            break  # writer nodes are handled by the caller, not here
        pred_id = compiler.predecessor_id(node.id, edges)
        assert pred_id is not None
        input_view = view_by_node[pred_id]
        join_view = f"node_{node.id}__join" if node.op == "transform.join" else None
        _validate_node_exprs(conn, node)
        sql = compiler.compile_transform_sql(node.op, node.params, input_view=input_view, join_view=join_view)
        view_name = f"node_{node.id}"
        conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
        view_by_node[node.id] = view_name
        stats.append(NodeStat(node.id, node.op, _view_row_count(conn, view_name)))
        if stop_at == node.id:
            return stats
    return stats


def _view_row_count(conn, view_name: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {_qi(view_name)}").fetchone()[0]


def preview_pipeline(
    *, session: Session | None, payload: PipelinePayload, tenant_id: str, user: User | None,
    up_to: str, endpoint_url: str, access_key: str, secret_key: str, base_uri: str, limit: int = 50,
) -> list[dict]:
    target = next((n for n in payload.nodes if n.id == up_to), None)
    if target is None:
        raise PipelineRuntimeError(f"node '{up_to}' not found")
    if target.kind == "writer":
        raise PipelineRuntimeError("preview cannot target a writer node")

    conn = open_connection(endpoint_url=endpoint_url, access_key=access_key, secret_key=secret_key)
    try:
        ordered, view_by_node = _prepare(conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri)
        _execute_transform_chain(conn, ordered, payload.edges, view_by_node, stop_at=up_to)
        rows = conn.execute(f"SELECT * FROM {_qi(view_by_node[up_to])} LIMIT {int(limit)}").fetchall()
        cols = [d[0] for d in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def _write_collection(session: Session, conn, *, node: PipelineNode, view_by_node: dict, tenant_id: str, user: User) -> NodeStat:
    p = WriterCollectionParams.model_validate(node.params)
    collection = _require_writable_collection(session, tenant_id=tenant_id, user=user, collection_id=p.collectionId)
    info = _table_info_for_collection(session, collection.table_name)
    # view_by_node[node.id] is set by the caller (run_pipeline) to the
    # predecessor's view name before calling this function.
    input_view = view_by_node[node.id]

    input_cols = {d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description}
    has_geometry = "geometry" in input_cols
    # Convertit la géométrie en GeoJSON DANS la requête DuckDB (ST_AsGeoJSON),
    # jamais en repassant un objet géométrie déjà récupéré comme paramètre
    # lié d'une requête ultérieure — un aller-retour fragile, non nécessaire.
    select_list = (
        f"* EXCLUDE (geometry), ST_AsGeoJSON(geometry) AS geometry" if has_geometry else "*"
    )
    rows = conn.execute(f"SELECT {select_list} FROM {_qi(input_view)}").fetchall()
    cols = [d[0] for d in conn.description]

    # Colonnes réservées de la collection CIBLE : jamais des "properties",
    # même contrat que app.features.validation (reserved) et
    # app.features.repository._property_columns. Le pk qui a pu traverser la
    # chaîne depuis le reader (utile pour la preview, une future jointure)
    # est écarté ici, jamais transmis comme propriété d'écriture — un
    # pipeline ré-émet des features comme n'importe quel client OGC (design
    # SP-15a §6.2), qui n'envoie jamais pk/tenant_id dans "properties".
    reserved_on_write = {info.pk_column, "tenant_id"}

    count = 0
    with rls_scope(session, tenant_id):
        for raw in rows:
            row = dict(zip(cols, raw))
            geometry = json.loads(row.pop("geometry")) if has_geometry and row.get("geometry") is not None else None
            for key in reserved_on_write:
                row.pop(key, None)
            properties = row
            feature = {"type": "Feature", "properties": properties, "geometry": geometry}
            errors = validate_feature(info, feature)
            if errors:
                raise PipelineRuntimeError(f"writer.collection: invalid row: {errors}")
            insert_feature(session, info, properties=properties, geometry=geometry)
            count += 1
    return NodeStat(node.id, node.op, count)


def _write_export(conn, s3_client, exports_bucket: str, *, node: PipelineNode, view_by_node: dict) -> NodeStat:
    p = WriterExportParams.model_validate(node.params)
    input_view = view_by_node[node.id]
    rows = conn.execute(f"SELECT * FROM {_qi(input_view)}").fetchall()
    columns = [d[0] for d in conn.description]
    if p.format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        writer.writerows(rows)
        body = buf.getvalue().encode("utf-8")
    else:
        features = [
            {"type": "Feature", "properties": dict(zip(columns, row)), "geometry": None}
            for row in rows
        ]
        body = json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")
    s3_client.put_object(Bucket=exports_bucket, Key=p.key, Body=body)
    return NodeStat(node.id, node.op, len(rows))


def run_pipeline(
    session: Session, *, payload: PipelinePayload, tenant_id: str, user: User,
    endpoint_url: str, access_key: str, secret_key: str, base_uri: str,
    s3_client=None, exports_bucket: str | None = None,
) -> list[NodeStat]:
    conn = open_connection(endpoint_url=endpoint_url, access_key=access_key, secret_key=secret_key)
    try:
        ordered, view_by_node = _prepare(conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri)
        stats = _execute_transform_chain(conn, ordered, payload.edges, view_by_node)
        for node in ordered:
            if node.kind != "writer":
                continue
            pred_id = compiler.predecessor_id(node.id, payload.edges)
            assert pred_id is not None
            view_by_node[node.id] = view_by_node[pred_id]
            if node.op == "writer.collection":
                stats.append(_write_collection(
                    session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
                ))
            elif node.op == "writer.export":
                assert s3_client is not None and exports_bucket is not None
                stats.append(_write_export(conn, s3_client, exports_bucket, node=node, view_by_node=view_by_node))
        return stats
    finally:
        conn.close()
