# SPDX-License-Identifier: Apache-2.0
"""Boucle d'écriture de `writer.collection` (F1 modes upsert/update/delete, F2 rejets).

`runtime._write_collection` garde les contrôles d'accès et les gardes (géo-limites, relations) ;
ce module lit la vue d'entrée DuckDB par lots et écrit dans la transaction UNIQUE du run
(annulation ou erreur = rien d'écrit, quarantaine comprise).

- append/insert/replace : comportement historique (une ligne invalide fait échouer le run, sauf
  `onInvalid="reject"`).
- upsert/update/delete : rapprochement par `keyColumns` ; `statusColumn` (detectChanges) trie les
  lignes ; une mise à jour identique n'écrit rien (rejeu idempotent) ; `delete` ne supprime que
  les clés fournies. Les mises à jour/suppressions sont journalisées (ARC-15, `entity_history`).
- Rejets : lignes invalides, clés absentes/dupliquées, `rejectWhenFalse` -> `<cible>__rejected`
  (créée à la demande, lisible par qui peut écrire la cible : propriétaire + groupes
  editor/manager de la cible, en lecture seule)."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.profile import _stat_selects  # lecture seule : mêmes stats que le profil
from app.audit.writer import write_audit
from app.collections import repository as collections_repo
from app.collections.ddl import apply_collection_ddl
from app.collections.introspection import ColumnInfo, TableInfo
from app.collections.introspection_pg import introspect_table
from app.features.repository import _geojson_out, _geometry_sql, insert_features
from app.features.rls import rls_scope
from app.features.validation import validate_for_write
from app.history import service as history
from app.history.models import EntityHistory
from app.pipelines.errors import PipelineCancelledError, PipelineRuntimeError
from app.quotas.service import QuotaExceededError
from app.sql_ident import quote_ident
from app.sql_ident import quote_ident_duckdb as _qi

_STATUS_OK = {"upsert": {"inserted", "updated"}, "update": {"updated"}, "delete": {"deleted"}}
_KEY_TYPES = {"string", "integer", "number", "boolean", "date", "enum"}
_FR = {
    "unknown_property": "propriété inconnue de la collection cible",
    "invalid_type": "type de valeur invalide",
    "invalid_enum": "valeur hors des choix autorisés",
    "out_of_domain": "valeur hors du domaine autorisé",
    "missing_required": "valeur obligatoire manquante",
    "unsupported_type": "colonne en lecture seule",
}


@dataclass
class WriteResult:
    replace_purged: int | None = None
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    rejected: int = 0
    rejected_collection: str | None = None
    rejects_by_rule: dict[str, int] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)

    @property
    def written(self) -> int:
        return self.inserted + self.updated + self.deleted


def _norm(col: ColumnInfo, v: Any) -> str:
    if col.type == "integer":
        return str(int(v))
    if col.type == "number":
        return repr(float(v))
    if col.type == "boolean":
        return str(bool(v))
    return str(v)


def _bind(col: ColumnInfo, v: Any) -> Any:
    if col.type == "integer":
        return int(v)
    if col.type == "number":
        return float(v)
    if col.type == "boolean":
        return bool(v)
    return v


def quality_report(
    conn, view: str, info: TableInfo, row_count: int, sensitive: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Taux de nulls (+ distincts/min/max) des colonnes de l'entrée présentes dans la cible,
    avec les agrégats de `analytics.profile._stat_selects` appliqués à la vue du run. Jamais
    les champs sensibles de la cible (GAP-22) : le rapport est lisible par qui lit le pipeline."""
    in_cols = {d[0] for d in conn.execute(f"SELECT * FROM {_qi(view)} LIMIT 0").description}
    cols = [
        c
        for c in info.columns
        if c.name in in_cols and c.type != "unsupported" and c.name not in sensitive
    ][:50]
    if not cols or row_count == 0:
        return {"rowCount": row_count, "columns": []}
    selects = [s for i, c in enumerate(cols) for s in _stat_selects(i, c.name, c.type)]
    cur = conn.execute(f"SELECT {', '.join(selects)} FROM {_qi(view)}")
    stats = dict(zip([d[0] for d in cur.description], cur.fetchone(), strict=True))
    out = []
    for i, c in enumerate(cols):
        n = int(stats[f"n{i}"])
        p: dict[str, Any] = {
            "name": c.name,
            "nonNull": n,
            "nulls": row_count - n,
            "nullRate": round((row_count - n) / row_count, 4),
        }
        if f"d{i}" in stats:
            p["distinct"] = int(stats[f"d{i}"])
        if f"lo{i}" in stats:
            p["min"], p["max"] = stats[f"lo{i}"], stats[f"hi{i}"]
        out.append(p)
    return {"rowCount": row_count, "columns": out}


def _ensure_quarantine(session: Session, target) -> str:
    """Crée (à la demande) `<cible>__rejected` et réaligne son partage sur celui de la cible :
    propriétaire identique, jamais publique, non éditable, groupes editor/manager -> viewer."""
    qid = f"{target.id}__rejected"[:63]
    if collections_repo.get_collection(session, tenant_id=target.tenant_id, collection_id=qid):
        col_id = qid
    else:
        t = quote_ident(session, qid)
        session.execute(
            text(
                f"CREATE TABLE public.{t} (id serial PRIMARY KEY, tenant_id text NOT NULL, "
                "source_row text, rule text, message text, run_id text)"
            )
        )
        info = introspect_table(session, qid)
        apply_collection_ddl(session, qid)
        try:
            col = collections_repo.create_collection(
                session,
                tenant_id=target.tenant_id,
                owner_id=target.owner_id,
                table_name=qid,
                title=f"{target.title} (rejets)",
                description=f"Lignes rejetées par les pipelines écrivant dans « {target.title} ».",
                is_public=False,
                pk_column=info.pk_column,
                geometry_column=None,
                geometry_type=None,
                srid=None,
                feature_count=0,
            )
        except QuotaExceededError as exc:
            # Le run échoue en bloc (la transaction est annulée par l'appelant : aucune écriture
            # partielle) plutôt que de perdre silencieusement les lignes rejetées.
            raise PipelineRuntimeError(
                "writer.collection: des lignes sont rejetées mais la collection de quarantaine "
                f"« {target.title} (rejets) » ne peut pas être créée : quota de collections "
                "atteint. Libérez un emplacement ou corrigez les données, puis relancez."
            ) from exc
        col.editable = False  # lecture seule via REST (le pipeline écrit en SQL direct)
        session.flush()
        write_audit(
            session,
            tenant_id=target.tenant_id,
            actor_id=target.owner_id,
            actor_kind="user",
            action="collection.create",
            object_type="collection",
            object_id=col.id,
            payload={"tableName": col.table_name, "quarantineOf": target.id},
        )
        col_id = col.id
    _sync_quarantine_shares(session, target, col_id)
    return col_id


def _sync_quarantine_shares(session: Session, target, col_id: str) -> None:
    """Réaligne le partage de la quarantaine sur la cible (editor/manager -> viewer) : appelé à
    CHAQUE run dès que la quarantaine existe, rejets ou non, pour retirer les groupes qui ont
    perdu l'accès à la cible."""
    session.execute(text("DELETE FROM collection_shares WHERE collection_id = :q"), {"q": col_id})
    session.execute(
        text(
            "INSERT INTO collection_shares (collection_id, group_id, tenant_id, role) "
            "SELECT :q, group_id, tenant_id, 'viewer' FROM collection_shares "
            "WHERE collection_id = :t AND role IN ('editor', 'manager')"
        ),
        {"q": col_id, "t": target.id},
    )


def _store_rejects(session: Session, target, rejects: list[tuple], run_id: str | None) -> str:
    qid = _ensure_quarantine(session, target)
    t = quote_ident(session, qid)
    session.execute(
        text(
            f"INSERT INTO public.{t} (tenant_id, source_row, rule, message, run_id) "
            "VALUES (:tid, :row, :rule, :msg, :run)"
        ),
        [
            {"tid": target.tenant_id, "row": r, "rule": rule, "msg": msg, "run": run_id}
            for r, rule, msg in rejects
        ],
    )
    session.execute(
        text(
            "UPDATE collections SET feature_count = COALESCE(feature_count, 0) + :n WHERE id = :i"
        ),
        {"n": len(rejects), "i": qid},
    )
    return qid


def _snapshots(session: Session, info: TableInfo, tenant_id: str, pks: list) -> dict[Any, dict]:
    """pk -> instantané {properties, geometry} (jamais découpé : rôle courant, pas de géo-limite
    puisque ces modes sont refusés sous limite géographique)."""
    if not pks:
        return {}
    t = quote_ident(session, info.table_name)
    props = [c.name for c in info.columns if c.name not in (info.pk_column, "tenant_id")]
    props = [p for p in props if p != info.geometry_column]
    sel = [quote_ident(session, info.pk_column)] + [quote_ident(session, p) for p in props]
    if info.geometry_column:
        sel.append(f"{_geojson_out(session, info)} AS __g")
    rows = session.execute(
        text(
            f"SELECT {', '.join(sel)} FROM public.{t} "
            f"WHERE tenant_id = :tid AND {quote_ident(session, info.pk_column)} = ANY(:pks)"
        ),
        {"pks": pks, "tid": tenant_id},
    ).mappings()
    out = {}
    for r in rows:
        g = r["__g"] if info.geometry_column else None
        out[r[info.pk_column]] = history.snapshot(
            {
                "properties": {p: r[p] for p in props},
                "geometry": json.loads(g) if g else None,
            }
        )
    return out


def _lookup(
    session: Session, info: TableInfo, tenant_id: str, keys: list[ColumnInfo], batch: list[tuple]
):
    """Lignes de la cible portant l'une des clés du lot : norm(clé) -> [pk, ...].
    Lecture en rôle propriétaire avec filtre `tenant_id` explicite : sous `gis_rls` les policies
    (dont `geo_limit`) sont évaluées ligne à ligne et rendent le balayage O(lignes × policy) ;
    ces modes sont refusés sous limite géographique, le tenant est le seul filtre RLS en jeu.
    `IN (VALUES ...)` = semi-jointure par hachage ; sans index sur `keyColumns` chaque lot balaie
    la cible (ponytail: indexer les clés métier de la cible au-delà de ~1 M lignes)."""
    t = quote_ident(session, info.table_name)
    cols = ", ".join(quote_ident(session, k.name) for k in keys)
    params: dict[str, Any] = {"tid": tenant_id}
    tuples = []
    for i, bound in enumerate(batch):
        names = []
        for j, v in enumerate(bound):
            params[f"k{i}_{j}"] = v
            names.append(f":k{i}_{j}")
        tuples.append(f"({', '.join(names)})")
    rows = session.execute(
        text(
            f"SELECT {quote_ident(session, info.pk_column)}, {cols} FROM public.{t} "
            f"WHERE tenant_id = :tid AND ({cols}) IN (VALUES {', '.join(tuples)})"
        ),
        params,
    ).all()
    out: dict[tuple, list] = {}
    for r in rows:
        out.setdefault(tuple(_norm(k, v) for k, v in zip(keys, r[1:], strict=True)), []).append(
            r[0]
        )
    return out


def _pg_types(session: Session, info: TableInfo) -> dict[str, str]:
    rows = session.execute(
        text(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = CAST(:t AS regclass) AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"t": "public." + quote_ident(session, info.table_name)},
    )
    return {name: typ for name, typ in rows.all()}


def _update_stmt(session: Session, info: TableInfo, cols: list[ColumnInfo], has_geom: bool):
    """UPDATE ensembliste (un seul aller-retour par lot) : les lignes arrivent en JSON et sont
    jointes par pk via `jsonb_to_recordset` ; les types viennent de `pg_attribute`. Le filtre
    IS DISTINCT FROM évite de réécrire une ligne identique (rejeu idempotent, pas de WAL)."""
    t = quote_ident(session, info.table_name)
    types = _pg_types(session, info)

    def q(n: str) -> str:
        return quote_ident(session, n)

    pk = q(info.pk_column)
    defs = [f'"__pk" {types[info.pk_column]}'] + [f"{q(c.name)} {types[c.name]}" for c in cols]
    sets = [f"{q(c.name)} = v.{q(c.name)}" for c in cols]
    diffs = [f"t.{q(c.name)} IS DISTINCT FROM v.{q(c.name)}" for c in cols]
    extra = ""
    if has_geom:
        defs.append('"__g" text')
        geom = _geometry_sql(info).replace(":__geom", 'x."__g"')
        extra = f', CASE WHEN x."__g" IS NULL THEN NULL ELSE {geom} END AS "__ng"'
        g = q(info.geometry_column)
        sets.append(f'{g} = v."__ng"')
        diffs.append(f'ST_AsEWKB(t.{g}) IS DISTINCT FROM ST_AsEWKB(v."__ng")')
    return text(
        f"UPDATE public.{t} AS t SET {', '.join(sets)} FROM (SELECT x.*{extra} FROM "
        f"jsonb_to_recordset(CAST(:rows AS jsonb)) AS x({', '.join(defs)})) AS v "
        f'WHERE t.{pk} = v."__pk" AND ({" OR ".join(diffs)})'
    )


def _journal(session, collection, ops: list[tuple], actor_id: str) -> None:
    """ARC-15 : une ligne `entity_history` par entité modifiée/supprimée (même transaction).
    ponytail: pas de purge de quota par entité (200) à l'écriture ; `history.purge_expired` borne
    par l'âge. À ajouter si une entité très mise à jour pose problème."""
    if not ops:
        return
    session.execute(
        EntityHistory.__table__.insert(),
        [
            {
                "tenant_id": collection.tenant_id,
                "collection_id": collection.id,
                "fid": str(fid),
                "op": op,
                "before": before,
                "after": after,
                "actor_id": actor_id,
            }
            for fid, op, before, after in ops
        ],
    )


def write_rows(
    session: Session,
    conn,
    *,
    input_view: str,
    p,
    collection,
    info: TableInfo,
    tenant_id: str,
    user,
    geo_limits,
    node_id: str,
    run_id: str | None,
    batch_size: int,
    on_progress: Callable[[int], None] | None,
    should_cancel: Callable[[], bool] | None,
    replace_purge: Callable[[], int | None],
    srid: int = 4326,
) -> WriteResult:
    mode = "append" if p.mode == "insert" else p.mode
    res = WriteResult()
    in_cols = [d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description]
    has_geom_in = "geometry" in in_cols
    # Le contrat d'écriture (`_geometry_sql`) attend du GeoJSON lon/lat 4326 : un flux en SRID
    # natif (reader.collection 2154…) est reprojeté ici, sinon double reprojection.
    gj = (
        "geometry"
        if srid in (0, 4326)
        else f"ST_Transform(geometry, 'EPSG:{int(srid)}', 'EPSG:4326', true)"
    )
    select_list = f"* EXCLUDE (geometry), ST_AsGeoJSON({gj}) AS geometry" if has_geom_in else "*"
    n_in = conn.execute(f"SELECT COUNT(*) FROM {_qi(input_view)}").fetchone()[0]
    sensitive = frozenset(collection.sensitive_fields or ())
    res.quality = quality_report(conn, input_view, info, n_in, sensitive)
    cursor = conn.execute(f"SELECT {select_list} FROM {_qi(input_view)}")
    cols = [d[0] for d in cursor.description]

    by_name = {c.name: c for c in info.columns}
    keys: list[ColumnInfo] = []
    if mode in ("upsert", "update", "delete"):
        for k in p.keyColumns:
            c = by_name.get(k)
            if c is None or k in (info.pk_column, "tenant_id", info.geometry_column):
                raise PipelineRuntimeError(f"writer.collection: key column '{k}' not in target")
            if c.type not in _KEY_TYPES:
                raise PipelineRuntimeError(
                    f"writer.collection: key column '{k}' has unsupported type '{c.type}'"
                )
            if k not in cols:
                raise PipelineRuntimeError(f"writer.collection: key column '{k}' not in input")
            keys.append(c)
    if p.statusColumn and p.statusColumn not in cols:
        raise PipelineRuntimeError(
            f"writer.collection: statusColumn '{p.statusColumn}' not in input"
        )
    for rc in p.rejectWhenFalse:
        if rc not in cols:
            raise PipelineRuntimeError(f"writer.collection: rejectWhenFalse '{rc}' not in input")
    reserved = {info.pk_column, "tenant_id", *p.rejectWhenFalse}
    if p.statusColumn:
        reserved.add(p.statusColumn)

    rejects: list[tuple] = []
    seen: set[tuple] = set()

    def reject(raw_row: dict, rule: str, message: str) -> None:
        res.rejected += 1
        res.rejects_by_rule[rule] = res.rejects_by_rule.get(rule, 0) + 1
        # GAP-22 : la quarantaine est lisible par des groupes qui ne lisent pas forcément les champs
        # sensibles de la cible : jamais de valeur sensible dans `source_row`. GAP-27 : ces groupes
        # peuvent être limités géographiquement, et la quarantaine (sans géométrie, hors RLS
        # spatiale) ne peut pas découper : la géométrie n'est jamais recopiée.
        safe = {k: v for k, v in raw_row.items() if k not in sensitive and k != "geometry"}
        rejects.append((json.dumps(safe, default=str, ensure_ascii=False), rule, message))

    if mode == "replace":
        with rls_scope(session, tenant_id, geo_limits=geo_limits):
            res.replace_purged = replace_purge()
    while True:
        raws = cursor.fetchmany(batch_size)
        if not raws:
            break
        journal: list[tuple] = []
        batch: list[dict] = []  # lignes retenues : {props, geom, key(norm), bound, status}
        for raw in raws:
            row = dict(zip(cols, raw, strict=True))
            source = dict(row)
            geometry = (
                json.loads(row.pop("geometry")) if has_geom_in and row.get("geometry") else None
            )
            if has_geom_in:
                row.pop("geometry", None)
            status = row.get(p.statusColumn) if p.statusColumn else None
            failed = next((rc for rc in p.rejectWhenFalse if row.get(rc) is False), None)
            if failed:
                reject(source, failed, f"règle de validation « {failed} » non satisfaite")
                continue
            for k in reserved:
                row.pop(k, None)
            key = bound = None
            if keys:
                vals = [source.get(k.name) for k in keys]
                if any(v is None for v in vals):
                    reject(source, "missing_key", "clé de rapprochement absente (valeur nulle)")
                    continue
                key = tuple(_norm(k, v) for k, v in zip(keys, vals, strict=True))
                if key in seen:
                    reject(source, "duplicate_key", "clé en doublon dans le flux d'entrée")
                    continue
                bound = tuple(_bind(k, v) for k, v in zip(keys, vals, strict=True))
            if p.statusColumn and mode in _STATUS_OK:
                if status not in _STATUS_OK[mode]:
                    res.unchanged += status == "unchanged"
                    continue
            if mode != "delete":
                errors = validate_for_write(
                    info, {"type": "Feature", "properties": row, "geometry": geometry}
                )
                if errors:
                    if p.onInvalid == "fail":
                        raise PipelineRuntimeError(f"writer.collection: invalid row: {errors}")
                    e = errors[0]
                    reject(
                        source,
                        e.get("code", "invalid"),
                        f"{e.get('field', '')} : {_FR.get(e.get('code'), e.get('message', ''))}",
                    )
                    continue
            if key is not None:
                seen.add(key)
            batch.append({"props": row, "geom": geometry, "key": key, "bound": bound})

        if mode in ("append", "replace"):
            with rls_scope(session, tenant_id, geo_limits=geo_limits):
                insert_features(session, info, [(b["props"], b["geom"]) for b in batch])
            res.inserted += len(batch)
        elif batch:
            journal = _match_and_write(
                session,
                info,
                keys,
                mode,
                batch,
                has_geom_in,
                res,
                scope=lambda: rls_scope(session, tenant_id, geo_limits=geo_limits),
                tenant_id=tenant_id,
            )
        _journal(session, collection, journal, user.id)  # hors rls_scope (cf. docstring history)
        if on_progress is not None:
            on_progress(res.written)
        if should_cancel is not None and should_cancel():
            raise PipelineCancelledError("run annulé")

    if rejects:
        res.rejected_collection = _store_rejects(session, collection, rejects, run_id)
    else:
        qid = f"{collection.id}__rejected"[:63]
        if collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=qid):
            _sync_quarantine_shares(session, collection, qid)
    if res.inserted or res.deleted:
        delta = res.inserted - res.deleted if mode in ("upsert", "update", "delete") else 0
        if delta:
            session.execute(
                text(
                    "UPDATE collections SET feature_count = COALESCE(feature_count, 0) + :d "
                    "WHERE id = :i"
                ),
                {"d": delta, "i": collection.id},
            )
    return res


def _match_and_write(
    session, info, keys, mode, batch, has_geom_in, res: WriteResult, *, scope, tenant_id
) -> list[tuple]:
    """Un lot : lectures en propriétaire (clés, avant/après), écritures sous `scope()` (RLS).
    Renvoie les lignes de journal ARC-15 (écrites par l'appelant, hors RLS)."""
    existing = _lookup(session, info, tenant_id, keys, [b["bound"] for b in batch])
    to_insert, to_update, to_delete = [], [], []  # to_update : (pk, b)
    for b in batch:
        pks = existing.get(b["key"], [])
        if mode == "delete":
            to_delete += pks
        elif not pks:
            if mode == "upsert":
                to_insert.append(b)
        else:
            to_update += [(pk, b) for pk in pks]
    journal: list[tuple] = []
    t = quote_ident(session, info.table_name)
    pk_col = quote_ident(session, info.pk_column)
    if to_delete:
        before = _snapshots(session, info, tenant_id, to_delete)
        with scope():
            gone = (
                session.execute(
                    text(f"DELETE FROM public.{t} WHERE {pk_col} = ANY(:pks) RETURNING {pk_col}"),
                    {"pks": to_delete},
                )
                .scalars()
                .all()
            )
        res.deleted += len(gone)
        journal += [(pk, "delete", before.get(pk), None) for pk in gone]
    if to_insert:
        with scope():
            insert_features(session, info, [(b["props"], b["geom"]) for b in to_insert])
        res.inserted += len(to_insert)
    if to_update:
        pks = [pk for pk, _ in to_update]
        before = _snapshots(session, info, tenant_id, pks)
        present = set().union(*(b["props"].keys() for _, b in to_update))
        ucols = [
            c
            for c in info.columns
            if c.name in present and c.type != "unsupported" and c.name != info.geometry_column
        ]
        stmt = _update_stmt(session, info, ucols, has_geom_in and bool(info.geometry_column))
        rows = []
        for pk, b in to_update:
            r: dict[str, Any] = {"__pk": pk, **{c.name: b["props"].get(c.name) for c in ucols}}
            if has_geom_in and info.geometry_column:
                r["__g"] = json.dumps(b["geom"]) if b["geom"] is not None else None
            rows.append(r)
        with scope():
            session.execute(
                stmt, {"rows": json.dumps(rows, default=str), "__srid": info.srid or 4326}
            )
        after = _snapshots(session, info, tenant_id, pks)
        for pk in pks:
            if before.get(pk) != after.get(pk):
                res.updated += 1
                journal.append((pk, "update", before.get(pk), after.get(pk)))
            else:
                res.unchanged += 1
    return journal
