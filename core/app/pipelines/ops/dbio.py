# SPDX-License-Identifier: Apache-2.0
"""Module de voie B — bases de données & formats tabulaires.
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

- `writer.connector.postgres.update` / `.delete` (FME DatabaseUpdater/DatabaseDeleter) :
  écriture ligne à ligne vers un Postgres externe, via un secret `postgres_dsn` du coffre.
  Écart au plan : pas de kind de secret dédié « écriture » — c'est à l'opérateur de n'y mettre
  qu'un rôle distant autorisé en écriture sur les seules tables voulues (moindre privilège).
  Le WHERE est TOUJOURS borné aux `keyColumns` (min 1, jamais de clé NULL) : aucun UPDATE/
  DELETE sans clé n'est constructible. Valeurs et clés = paramètres liés (SQLAlchemy Core),
  identifiants quotés par le dialecte et vérifiés contre la table distante réfléchie ; une
  seule transaction distante (tout ou rien) ; garde d'egress + épinglage DNS du DSN ; audit
  commité AVANT l'écriture distante. Pas d'aperçu : un nœud writer n'est jamais prévisualisable
  (`preview_pipeline` le refuse). Rejeu après reprise sûr : les deux modes sont idempotents.
- `reader.connector.googlesheets` : lecture d'une plage via l'API Sheets v4, secret
  `bearer_token` (jeton OAuth) ou `api_key` lié à son `baseUrl`, session HTTP gardée.

Ne jamais importer contracts/runtime/registries au niveau module (cycle d'import)."""

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import pandas as pd
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.pipelines.errors import PipelineCancelledError, PipelineRuntimeError
from app.pipelines.ops.operation_contract import OperationContract
from app.sql_ident import quote_ident_duckdb as _qi

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}

_IDENT = r"[A-Za-z_][A-Za-z0-9_$]*"
_TABLE_RE = re.compile(rf"^({_IDENT}\.)?{_IDENT}$")


# --------------------------------------------------------------------------- écriture externe


class _ExternalWriteParams(BaseModel):
    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    table: str = Field(..., max_length=200, description="`table` ou `schema.table`")
    keyColumns: list[str] = Field(..., min_length=1, max_length=8)

    @model_validator(mode="after")
    def _check(self):
        if not _TABLE_RE.match(self.table):
            raise ValueError(
                "table: forme attendue `table` ou `schema.table` (identifiants simples)"
            )
        if len(set(self.keyColumns)) != len(self.keyColumns) or not all(self.keyColumns):
            raise ValueError("keyColumns: colonnes vides ou dupliquées")
        return self


class WriterConnectorPostgresUpdateParams(_ExternalWriteParams):
    """Met à jour, dans une table d'une base Postgres externe, `updateColumns` de la ligne dont
    les colonnes clés valent celles de la ligne reçue (une requête UPDATE par ligne, dans une
    seule transaction). Aucune mise à jour sans clé ; une clé NULL fait échouer le nœud. Les
    lignes sans correspondance distante sont comptées (`unmatched`), pas créées."""

    updateColumns: list[str] = Field(..., min_length=1, max_length=100)

    @model_validator(mode="after")
    def _disjoint(self):
        if set(self.updateColumns) & set(self.keyColumns):
            raise ValueError("updateColumns ne doit pas contenir de colonne clé")
        return self


class WriterConnectorPostgresDeleteParams(_ExternalWriteParams):
    """Supprime, dans une table d'une base Postgres externe, les lignes dont les colonnes clés
    valent celles de chaque ligne reçue (une requête DELETE par ligne, dans une seule
    transaction). Aucune suppression sans clé ; une clé NULL fait échouer le nœud."""


def _max_rows() -> int:
    from app.pipelines.connector_runtime import _max_rows as m

    return m()


def _dsn_engine(dsn: str):
    """Engine SQLAlchemy vers un Postgres externe : même garde que `_stream_sql` (egress sur
    l'hôte du DSN, épinglage sur l'IP validée, délais de connexion/requête)."""
    import sqlalchemy as sa

    from app.pipelines import connector_runtime as cr
    from app.pipelines.egress import assert_dsn_egress_allowed, dsn_pin_connect_args

    url = sa.engine.make_url(dsn)
    if not url.get_backend_name().startswith("postgresql"):
        raise PipelineRuntimeError("writer.connector.postgres: DSN non PostgreSQL")
    assert_dsn_egress_allowed(dsn)
    args = {**cr._timeout_connect_args("postgresql", url.host), **dsn_pin_connect_args(dsn)}
    return sa.create_engine(dsn, connect_args=args)


def _external_write(
    session,
    conn,
    *,
    node,
    view_by_node: dict,
    tenant_id: str,
    user,
    model: type[_ExternalWriteParams],
    update: bool,
    should_cancel: Callable[[], bool] | None = None,
    **_extra: Any,
):
    import sqlalchemy as sa

    from app.pipelines.connector_runtime import PostgresSecretResolver
    from app.pipelines.runtime import NodeStat

    op = node.op
    p = model.model_validate(node.params)
    try:
        payload = PostgresSecretResolver(session, tenant_id, user).get(p.secretName)
    except KeyError:
        raise PipelineRuntimeError(f"{op}: secret '{p.secretName}' not found") from None
    if payload.kind != "postgres_dsn":
        raise PipelineRuntimeError(f"{op}: secret has kind '{payload.kind}', expected postgres_dsn")

    set_cols: list[str] = list(getattr(p, "updateColumns", []))
    cols = [*p.keyColumns, *set_cols]
    view = view_by_node[node.id]
    desc = conn.execute(f"SELECT * FROM {_qi(view)} LIMIT 0").description
    in_cols = {d[0]: d[1] for d in desc}
    if missing := [c for c in cols if c not in in_cols]:
        raise PipelineRuntimeError(f"{op}: column(s) not found in input: {missing}")
    if any(in_cols[c].id == "geometry" for c in cols):
        raise PipelineRuntimeError(f"{op}: geometry columns are not supported")
    limit = _max_rows()
    rows = conn.execute(
        f"SELECT {', '.join(_qi(c) for c in cols)} FROM {_qi(view)} LIMIT {limit + 1}"
    ).fetchall()
    if len(rows) > limit:
        raise PipelineRuntimeError(f"{op}: plafond de {limit} lignes dépassé")
    nk = len(p.keyColumns)
    if any(v is None for r in rows for v in r[:nk]):
        raise PipelineRuntimeError(f"{op}: a key column is NULL (refused, never an open WHERE)")
    if not rows:
        return NodeStat(node.id, op, 0, {"unmatched": 0})

    schema, _, name = p.table.rpartition(".")
    engine = _dsn_engine(payload.dsn)
    try:
        remote = sa.Table(
            name, sa.MetaData(), schema=schema or None, autoload_with=engine
        )  # NoSuchTableError si absente ; colonnes quotées par le dialecte
        if missing := [c for c in cols if c not in remote.c]:
            raise PipelineRuntimeError(f"{op}: column(s) not found in '{p.table}': {missing}")
        where = sa.and_(
            *(remote.c[k] == sa.bindparam(f"k_{i}") for i, k in enumerate(p.keyColumns))
        )
        if update:
            stmt = (
                sa.update(remote)
                .where(where)
                .values({c: sa.bindparam(f"v_{i}") for i, c in enumerate(set_cols)})
            )
        else:
            stmt = sa.delete(remote).where(where)
        # Audit AVANT l'écriture distante (l'effet est irréversible), dans une session courte
        # SÉPARÉE : commiter `session` casserait la transaction du run (rollback F5).
        with Session(session.get_bind()) as audit_session:
            write_audit(
                audit_session,
                tenant_id=tenant_id,
                actor_id=user.id,
                actor_kind="user",
                action="pipeline.external_write",
                object_type="connector_secret",
                object_id=p.secretName,
                payload={"op": op, "table": p.table, "rows": len(rows)},
            )
            audit_session.commit()
        affected = 0
        # ponytail: une requête par ligne (rowcount fiable, une transaction) ; executemany
        # par lots si le débit devient limitant.
        with engine.begin() as db:
            for r in rows:
                if should_cancel is not None and should_cancel():
                    raise PipelineCancelledError(f"{op}: cancelled")  # rollback distant
                binds = {f"k_{i}": v for i, v in enumerate(r[:nk])}
                binds |= {f"v_{i}": v for i, v in enumerate(r[nk:])}
                affected += db.execute(stmt, binds).rowcount
    finally:
        engine.dispose()
    return NodeStat(
        node.id, op, affected, {"unmatched": max(len(rows) - affected, 0) if update else 0}
    )


def _write_update(session, conn, **kw):
    return _external_write(
        session, conn, model=WriterConnectorPostgresUpdateParams, update=True, **kw
    )


def _write_delete(session, conn, **kw):
    return _external_write(
        session, conn, model=WriterConnectorPostgresDeleteParams, update=False, **kw
    )


WRITERS["writer.connector.postgres.update"] = _write_update
WRITERS["writer.connector.postgres.delete"] = _write_delete
for _op, _model in (
    ("writer.connector.postgres.update", WriterConnectorPostgresUpdateParams),
    ("writer.connector.postgres.delete", WriterConnectorPostgresDeleteParams),
):
    CONTRACTS.append(
        OperationContract(
            op=_op,
            kind="writer",
            params_schema=_model,
            engine="python",
            engine_license="MIT (SQLAlchemy)",
        )
    )


# --------------------------------------------------------------------------- Google Sheets

_SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
_SHEETS_MAX_BYTES = 50 * 1024 * 1024


class ReaderConnectorGoogleSheetsParams(BaseModel):
    """Lit une plage d'une feuille Google Sheets (API Sheets v4) : la première ligne de la plage
    donne les noms de colonnes, les suivantes les enregistrements. `secretName` référence un
    secret bearer_token (jeton OAuth) ou api_key (feuille publique) lié à
    `https://sheets.googleapis.com/`."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    spreadsheetId: str = Field(..., pattern=r"^[A-Za-z0-9_-]{10,100}$")
    range: str = Field(
        "A:ZZ", min_length=1, max_length=200, description="Plage A1, ex. Feuille1!A:F"
    )


def _sheet_frame(values: list[list]) -> pd.DataFrame:
    if not values:
        raise PipelineRuntimeError("reader.connector.googlesheets: empty range")
    header = [str(h).strip() for h in values[0]]
    if not all(header) or len(set(header)) != len(header):
        raise PipelineRuntimeError(
            "reader.connector.googlesheets: header row has empty or duplicate names"
        )
    data = {h: [] for h in header}
    for row in values[1:]:
        for i, h in enumerate(header):
            data[h].append(row[i] if i < len(row) else None)
    # Colonne numérique/booléenne homogène conservée, sinon texte (types mixtes de Sheets).
    for h, col in data.items():
        kinds = {type(v) for v in col if v is not None}
        if len(kinds) > 1 and kinds != {int, float}:
            data[h] = [None if v is None else str(v) for v in col]
    return pd.DataFrame(data)


def read_googlesheets(
    conn, *, session, tenant_id, node_id, params, view_name, user, base_uri
) -> int:
    from app.pipelines.connector_runtime import PostgresSecretResolver, _max_rows, _url_within_scope
    from app.pipelines.egress import build_guarded_session

    p = ReaderConnectorGoogleSheetsParams.model_validate(params)
    op = "reader.connector.googlesheets"
    try:
        payload = PostgresSecretResolver(session, tenant_id, user).get(p.secretName)
    except KeyError:
        raise PipelineRuntimeError(f"{op}: secret '{p.secretName}' not found") from None
    if payload.kind not in ("bearer_token", "api_key"):
        raise PipelineRuntimeError(
            f"{op}: secret has kind '{payload.kind}', expected bearer_token or api_key"
        )
    url = f"{_SHEETS_BASE}/{p.spreadsheetId}/values/{quote(p.range, safe='!:')}"
    # REV-294 : le secret n'est envoyé que sous la portée (baseUrl) à laquelle il est lié.
    if not payload.baseUrl or not _url_within_scope(payload.baseUrl, url):
        raise PipelineRuntimeError(
            f"{op}: secret baseUrl must cover '{_SHEETS_BASE}' (set it on the secret)"
        )
    headers: dict[str, str] = {}
    query: dict[str, str] = {"valueRenderOption": "UNFORMATTED_VALUE", "majorDimension": "ROWS"}
    if payload.kind == "bearer_token":
        headers["Authorization"] = f"Bearer {payload.token}"
    elif payload.location == "header":
        headers[payload.key] = payload.value
    else:
        query[payload.key] = payload.value
    sess = build_guarded_session()
    try:
        with sess.get(url, headers=headers, params=query, stream=True) as r:
            if r.status_code != 200:
                raise PipelineRuntimeError(f"{op}: Google Sheets API answered HTTP {r.status_code}")
            body = bytearray()
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > _SHEETS_MAX_BYTES:
                    raise PipelineRuntimeError(f"{op}: response larger than the byte cap")
    finally:
        sess.close()
    import json

    try:
        values = json.loads(body).get("values") or []
    except (ValueError, AttributeError) as exc:
        raise PipelineRuntimeError(f"{op}: invalid JSON answer from Google Sheets") from exc
    if len(values) - 1 > _max_rows():
        raise PipelineRuntimeError(f"{op}: plafond de {_max_rows()} lignes dépassé")
    df = _sheet_frame(values)
    conn.register("_gs_frame", df)
    try:
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT * FROM _gs_frame")
    finally:
        conn.unregister("_gs_frame")
    return 4326


READERS["reader.connector.googlesheets"] = read_googlesheets
CONTRACTS.append(
    OperationContract(
        op="reader.connector.googlesheets",
        kind="reader",
        params_schema=ReaderConnectorGoogleSheetsParams,
        engine="duckdb",
        engine_license="MIT (DuckDB) ; API REST Google via requests (Apache-2.0)",
    )
)
