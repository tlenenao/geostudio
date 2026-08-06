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
from app.audit.writer import write_audit
from app.collections import repository as collections_repo
from app.collections.introspection import TableInfo, TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, DatasetPayload, PipelineNode, PipelinePayload
from app.features.repository import insert_feature
from app.features.rls import rls_scope
from app.features.validation import validate_feature
from app.items import repository as items_repo
from app.pipelines import compiler
from app.pipelines.expr_validation import validate_bounded_expr
from app.pipelines.ops.schemas import (
    ReaderCollectionParams, TransformAggregateParams, TransformCountWithinParams,
    TransformDeriveParams, TransformFilterParams, TransformH3AggregateParams,
    TransformIntersectionParams, TransformJoinParams, WriterCollectionParams,
    WriterDatasetParams, WriterExportParams,
)
from app.sharing.authorization import can
from app.users.models import User

_JOIN_PARAM_MODELS: dict[str, type] = {
    "transform.join": TransformJoinParams,
    "transform.intersection": TransformIntersectionParams,
    "transform.countWithin": TransformCountWithinParams,
}


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
    elif node.op == "transform.h3Aggregate":
        p = TransformH3AggregateParams.model_validate(node.params)
        for metric_expr in p.metrics.values():
            validate_bounded_expr(conn, metric_expr)


def _prepare(
    conn, session: Session, payload: PipelinePayload, *, tenant_id: str, user: User, base_uri: str,
) -> tuple[list[PipelineNode], dict[str, str], dict[str, int], dict[str, int]]:
    """Passe 1 : matérialise tous les readers (+ le withCollectionId de
    chaque transform.join/intersection/countWithin), puis verrouille.
    Retourne (ordre topologique, view_name par node.id, srid par node.id
    pour les readers, srid par node.id pour la vue __join des 3 op
    binaires) — writer nodes n'ont pas encore de vue."""
    ordered = compiler.topological_order(payload.nodes, payload.edges)
    view_by_node: dict[str, str] = {}
    srid_by_node: dict[str, int] = {}

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
        srid_by_node[node.id] = table_info.srid or 4326

    join_srid_by_node: dict[str, int] = {}
    for node in ordered:
        model = _JOIN_PARAM_MODELS.get(node.op)
        if model is None:
            continue
        p = model.model_validate(node.params)
        table_name = _require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=p.withCollectionId,
        )
        table_info = _table_info_for_collection(session, table_name)
        join_view = f"node_{node.id}__join"
        _materialize_reader(
            conn, view_name=join_view, base_uri=base_uri, tenant_id=tenant_id,
            collection_id=p.withCollectionId, table_info=table_info,
        )
        join_srid_by_node[node.id] = table_info.srid or 4326

    _lock_down(conn)
    return ordered, view_by_node, srid_by_node, join_srid_by_node


def _execute_transform_chain(
    conn, ordered: list[PipelineNode], edges, view_by_node: dict[str, str],
    srid_by_node: dict[str, int], join_srid_by_node: dict[str, int],
    *, stop_at: str | None = None,
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
        input_srid = srid_by_node[pred_id]
        join_view = f"node_{node.id}__join" if node.op in _JOIN_PARAM_MODELS else None
        join_srid = join_srid_by_node.get(node.id)
        _validate_node_exprs(conn, node)
        try:
            output_srid = compiler.transform_output_srid(
                node.op, node.params, input_srid=input_srid, join_srid=join_srid,
            )
        except ValueError as exc:
            raise PipelineRuntimeError(str(exc)) from exc
        sql = compiler.compile_transform_sql(
            node.op, node.params, input_view=input_view, join_view=join_view, input_srid=input_srid,
        )
        view_name = f"node_{node.id}"
        conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
        view_by_node[node.id] = view_name
        srid_by_node[node.id] = output_srid
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
        ordered, view_by_node, srid_by_node, join_srid_by_node = _prepare(
            conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri,
        )
        _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node, stop_at=up_to,
        )
        view_name = view_by_node[up_to]
        # Même conversion que _write_collection : DuckDB renvoie "geometry" en
        # WKB (bytes), que jsonable_encoder (route FastAPI) ne sait pas
        # décoder — on convertit en GeoJSON ici, au point de sortie de la
        # preview, plutôt que de porter du GeoJSON à travers toute la chaîne
        # de transforms intermédiaire (Phase 1 n'a aucune op spatiale).
        input_cols = {d[0] for d in conn.execute(f"SELECT * FROM {_qi(view_name)} LIMIT 0").description}
        has_geometry = "geometry" in input_cols
        select_list = (
            "* EXCLUDE (geometry), ST_AsGeoJSON(geometry) AS geometry" if has_geometry else "*"
        )
        rows = conn.execute(f"SELECT {select_list} FROM {_qi(view_name)} LIMIT {int(limit)}").fetchall()
        cols = [d[0] for d in conn.description]
        result = [dict(zip(cols, r)) for r in rows]
        if has_geometry:
            # La colonne contient une chaîne GeoJSON (ST_AsGeoJSON) : on la
            # décode en objet pour que la réponse HTTP porte une géométrie
            # GeoJSON réelle, pas une chaîne-dans-une-chaîne.
            for row in result:
                if row.get("geometry") is not None:
                    row["geometry"] = json.loads(row["geometry"])
        return result
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


def _write_dataset(
    session: Session, conn, *, node: PipelineNode, view_by_node: dict, tenant_id: str, user: User,
) -> NodeStat:
    p = WriterDatasetParams.model_validate(node.params)
    # Réutilise _write_collection TEL QUEL (même chemin d'écriture OGC
    # Features) : writer.dataset n'introduit aucune primitive d'écriture, il
    # catalogue seulement le résultat comme item "dataset" ensuite (design
    # §4 point 1). Le node synthétique porte le même id que node.id : c'est
    # ainsi que _write_collection retrouve la bonne entrée de view_by_node
    # (posée par l'appelant, run_pipeline, avant le dispatch).
    collection_node = PipelineNode(
        id=node.id, kind="writer", op="writer.collection", params={"collectionId": p.collectionId},
    )
    write_stat = _write_collection(
        session, conn, node=collection_node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
    )

    if p.datasetId is not None:
        facts = items_repo.get_access_facts(session, tenant_id=tenant_id, item_id=p.datasetId)
        if facts is None or not can(session, user_id=user.id, action="write", item=facts):
            raise PipelineRuntimeError(f"dataset '{p.datasetId}' is not writable")
        existing = configs_repo.get_config_by_item(session, p.datasetId)
        if existing is None or existing.config.kind != "dataset":
            raise PipelineRuntimeError(f"dataset '{p.datasetId}' not found")
        current = existing.config.dataset
        assert current is not None
        # Reconstruit un DatasetPayload frais (pas model_copy sur lui-même) :
        # source/collectionId changent, tout le reste (columns, timeField,
        # reactsToExtent, crossFilterLinks) est copié tel quel, jamais
        # régénéré par le run (design §4).
        updated_dataset = DatasetPayload(
            source="collection", collectionId=p.collectionId,
            columns=current.columns, timeField=current.timeField,
            reactsToExtent=current.reactsToExtent, crossFilterLinks=current.crossFilterLinks,
        )
        # model_copy (pas de re-validation) est sûr ici : seul le champ
        # "dataset" change, et il porte déjà un DatasetPayload fraîchement
        # validé par son propre constructeur ci-dessus ; le reste de
        # existing.config a déjà été validé lors de sa sauvegarde d'origine.
        updated_config = existing.config.model_copy(update={"dataset": updated_dataset})
        configs_repo.update_config(session, existing.id, updated_config, tenant_id=tenant_id)
        write_audit(
            session, tenant_id=tenant_id, actor_id=user.id, actor_kind="user",
            action="config.update", object_type="config", object_id=existing.id,
            payload={"pipelineNodeId": node.id},
        )
    else:
        assert p.title is not None  # enforced by WriterDatasetParams' model_validator
        item = items_repo.create_item(
            session, tenant_id=tenant_id, owner_id=user.id, resource_type="dataset", title=p.title,
        )
        new_config = BuilderConfig(
            kind="dataset", dataset=DatasetPayload(source="collection", collectionId=p.collectionId),
        )
        config_result = configs_repo.create_config(session, new_config, item_id=item.id, tenant_id=tenant_id)
        write_audit(
            session, tenant_id=tenant_id, actor_id=user.id, actor_kind="user",
            action="item.create", object_type="item", object_id=item.id,
            payload={"title": p.title},
        )
        write_audit(
            session, tenant_id=tenant_id, actor_id=user.id, actor_kind="user",
            action="config.create", object_type="config", object_id=config_result.id,
            payload={"title": p.title, "kind": "dataset"},
        )
    return NodeStat(node.id, node.op, write_stat.rowCount)


def _write_export(conn, s3_client, exports_bucket: str, *, node: PipelineNode, view_by_node: dict) -> NodeStat:
    p = WriterExportParams.model_validate(node.params)
    input_view = view_by_node[node.id]
    # Même conversion que _write_collection/preview_pipeline : la géométrie
    # brute (WKB bytes) casse json.dumps (geojson) et n'a aucun sens en
    # cellule CSV — on la convertit en chaîne GeoJSON ici, au point de
    # sortie de l'export.
    input_cols = {d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description}
    has_geometry = "geometry" in input_cols
    select_list = (
        "* EXCLUDE (geometry), ST_AsGeoJSON(geometry) AS geometry" if has_geometry else "*"
    )
    rows = conn.execute(f"SELECT {select_list} FROM {_qi(input_view)}").fetchall()
    columns = [d[0] for d in conn.description]
    if p.format == "csv":
        # La colonne "geometry" contient désormais une chaîne GeoJSON : une
        # valeur de cellule CSV utile, pas de traitement supplémentaire requis.
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        writer.writerows(rows)
        body = buf.getvalue().encode("utf-8")
    else:
        features = []
        for row in rows:
            properties = dict(zip(columns, row))
            # La géométrie ne doit apparaître qu'au niveau "geometry" du
            # Feature, jamais dupliquée dans "properties" (même contrat que
            # _write_collection).
            geometry = None
            if has_geometry:
                geometry_json = properties.pop("geometry", None)
                geometry = json.loads(geometry_json) if geometry_json is not None else None
            features.append({"type": "Feature", "properties": properties, "geometry": geometry})
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
        ordered, view_by_node, srid_by_node, join_srid_by_node = _prepare(
            conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri,
        )
        stats = _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node,
        )
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
            elif node.op == "writer.dataset":
                stats.append(_write_dataset(
                    session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
                ))
        return stats
    finally:
        conn.close()
