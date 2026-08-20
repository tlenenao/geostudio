# SPDX-License-Identifier: Apache-2.0
"""Matérialisation dlt des deux op reader.connector.* (design SP-15f §3) —
chaque appel exécute un vrai pipeline dlt vers un fichier DuckDB scratch
dédié, l'ATTACH en lecture seule dans la connexion du runtime, sélectionne
la table racine "records" en TEMP TABLE, puis nettoie (finally). Aucun état
dlt ne survit à un appel (destination ET pipelines_dir scratch, supprimés
ensemble)."""

import os

# Doit précéder `import dlt` : la télémétrie anonyme de dlt est activée par
# défaut (design SP-15f Global Constraints) — un worker ne doit jamais
# téléphoner à l'extérieur par variable d'environnement oubliée.
os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")

import shutil
import tempfile
import uuid

import dlt
import sqlalchemy as sa
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.auth import (
    APIKeyAuth,
    BearerTokenAuth,
    HttpBasicAuth,
    OAuth2ClientCredentials,
)
from dlt.sources.helpers.rest_client.paginators import (
    JSONResponseCursorPaginator,
    OffsetPaginator,
    PageNumberPaginator,
    SinglePagePaginator,
)
from sqlalchemy.orm import Session

from app.analytics.sql_sandbox import SqlSandboxError, parse_ast, validate_select_only
from app.pipelines.egress import EgressBlockedError, build_guarded_session
from app.pipelines.ops.schemas import ReaderConnectorPostgresParams, ReaderConnectorRestParams
from app.secrets import repository as secrets_repo
from app.secrets.schemas import SecretPayload

_REST_SECRET_KINDS = {"api_key", "bearer_token", "basic_auth", "oauth2_client_credentials"}


def _qi(name: str) -> str:
    # Duplication délibérée (3e copie du dépôt) — cf. runtime.py, même
    # rationale : helper de 2 lignes, pas un import inter-module d'un nom
    # `_`-préfixé.
    return '"' + name.replace('"', '""') + '"'


class ConnectorRuntimeError(Exception):
    """Traduite en PipelineRuntimeError par runtime.py (Task 5) — définie
    ici plutôt qu'importée de runtime.py pour éviter un import circulaire
    (runtime.py importe ce module)."""


def _resolve_secret(
    session: Session, tenant_id: str, secret_name: str | None
) -> SecretPayload | None:
    if secret_name is None:
        return None
    payload = secrets_repo.get_secret_payload(session, tenant_id=tenant_id, name=secret_name)
    if payload is None:
        raise ConnectorRuntimeError(f"secret '{secret_name}' not found")
    return payload


def _build_auth(payload: SecretPayload | None):
    if payload is None:
        return None
    if payload.kind not in _REST_SECRET_KINDS:
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable by reader.connector.rest "
            f"(expected one of {sorted(_REST_SECRET_KINDS)})"
        )
    if payload.kind == "bearer_token":
        return BearerTokenAuth(token=payload.token)
    if payload.kind == "api_key":
        return APIKeyAuth(name=payload.key, api_key=payload.value, location=payload.location)
    if payload.kind == "basic_auth":
        return HttpBasicAuth(payload.username, payload.password)
    return OAuth2ClientCredentials(
        access_token_url=payload.tokenUrl,
        client_id=payload.clientId,
        client_secret=payload.clientSecret,
        # `session=` est indispensable ici : sans lui, dlt retombe sur son
        # propre `requests.session` par défaut (non gardé) pour l'échange de
        # jeton dans `obtain_token()` — seul des 4 kinds de secret REST à
        # faire sa propre requête plutôt que d'ajouter des en-têtes/paramètres
        # à la session déjà gardée passée à `RESTClient` (design SP-15f §5.1).
        session=build_guarded_session(),
    )


def _build_paginator(paginator: str, config: dict):
    if paginator == "none":
        # Passer un paginateur explicite plutôt que None : sans lui, dlt
        # retombe sur sa détection automatique à la première page et logge
        # un WARNING ("Fallback paginator used...") à chaque appel — bruit
        # de log pur puisqu'on sait déjà qu'il n'y a qu'une page (design §2,
        # paginator="none" est le défaut explicite du modèle de paramètres).
        return SinglePagePaginator()
    if paginator == "page_number":
        # `total_path` par défaut de dlt ("total") suppose un corps de
        # réponse en objet JSON avec un champ de total — nos réponses REST
        # sont des tableaux JSON bruts (design §2, `recordsPath` seulement
        # pour les corps enveloppés). Sans total_path, dlt s'appuie sur
        # `stop_after_empty_page` (défaut True) : une page vide arrête la
        # pagination — c'est le contrat qu'on veut ici.
        return PageNumberPaginator(
            base_page=config.get("basePage", 1),
            page_param=config.get("pageParam", "page"),
            maximum_page=config.get("maximumPage"),
            total_path=None,
        )
    if paginator == "offset":
        return OffsetPaginator(
            limit=config["limit"],
            offset_param=config.get("offsetParam", "offset"),
            limit_param=config.get("limitParam", "limit"),
            total_path=config.get("totalPath"),
        )
    if paginator == "cursor":
        return JSONResponseCursorPaginator(
            cursor_path=config.get("cursorPath", "cursors.next"),
            cursor_param=config.get("cursorParam", "cursor"),
        )
    raise ConnectorRuntimeError(f"unknown paginator '{paginator}'")


def _find_egress_blocked_cause(exc: BaseException) -> EgressBlockedError | None:
    # dlt (et, dans une moindre mesure, DuckDB) enveloppe toute exception
    # levée pendant l'extraction dans ses propres types
    # (ResourceExtractionError, PipelineStepFailed...), chaînés via
    # `__cause__`/`__context__` — vérifié empiriquement sur le cas OAuth2
    # (cf. test_materialize_rest_connector_oauth2_token_exchange_goes_...),
    # jamais laissé tel quel par dlt. On déroule la chaîne pour retrouver
    # l'EgressBlockedError d'origine, quelle que soit sa profondeur, plutôt
    # que de supposer un seul niveau d'enveloppe.
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, EgressBlockedError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _run_dlt_and_attach(conn, resource, *, node_id: str, view_name: str) -> None:
    scratch_dir = tempfile.mkdtemp(prefix=f"sp15f-{node_id}-")
    db_path = f"{scratch_dir}/extract.duckdb"
    try:
        pipeline = dlt.pipeline(
            pipeline_name=f"sp15f-{node_id}-{uuid.uuid4().hex}",
            destination=dlt.destinations.duckdb(db_path),
            dataset_name="pipeline_dataset",
            pipelines_dir=f"{scratch_dir}/dlt-home",
        )
        try:
            pipeline.run(resource)
            conn.execute(f"ATTACH '{db_path}' AS dlt_extract (READ_ONLY)")
            try:
                cols = [
                    d[0]
                    for d in conn.execute(
                        "SELECT * FROM dlt_extract.pipeline_dataset.records LIMIT 0"
                    ).description
                    if d[0] not in {"_dlt_id", "_dlt_load_id"}
                ]
                select_list = ", ".join(_qi(c) for c in cols)
                conn.execute(
                    f"CREATE TEMP TABLE {_qi(view_name)} AS "
                    f"SELECT {select_list} FROM dlt_extract.pipeline_dataset.records"
                )
            finally:
                conn.execute("DETACH dlt_extract")
        except ConnectorRuntimeError:
            # Ne devrait pas se produire aujourd'hui (rien dans ce bloc ne
            # lève ConnectorRuntimeError directement), mais si un jour un
            # appel interne en levait une, elle doit ressortir telle quelle
            # plutôt que d'être ré-enveloppée une seconde fois.
            raise
        except Exception as exc:
            # Toute autre défaillance EN COURS d'extraction (pas au
            # pré-flight, déjà couvert par les levées explicites plus haut
            # dans ce module) : la garde SSRF bloquant l'URL de DONNÉES (pas
            # seulement l'URL de jeton OAuth2, déjà couverte), une erreur
            # HTTP distante, une connexion/requête Postgres en échec, une
            # réponse JSON malformée... Traduite ici en ConnectorRuntimeError
            # pour que runtime.py._prepare() (qui ne traduit que ce type)
            # produise le même traitement propre 400/actionnable qu'un rejet
            # pré-flight, plutôt que de laisser fuiter un type dlt brut
            # jusqu'à un 500 générique (routes.py) ou un
            # "erreur interne : ..." opaque (jobs.py).
            egress_cause = _find_egress_blocked_cause(exc)
            if egress_cause is not None:
                raise ConnectorRuntimeError(f"egress blocked: {egress_cause}") from exc
            # Message borné et non-fuyant : vérifié empiriquement (pas
            # supposé) qu'un échec de connexion/requête psycopg via
            # SQLAlchemy ne fait jamais apparaître le mot de passe du DSN
            # dans str(exc), que ce soit un refus de connexion ("Connection
            # refused") ou un échec d'authentification ("password
            # authentication failed") — aucune des deux formes n'inclut le
            # DSN complet ni le mot de passe.
            raise ConnectorRuntimeError(f"reader.connector extraction failed: {exc}") from exc
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def materialize_rest_connector(
    conn,
    *,
    session: Session,
    tenant_id: str,
    node_id: str,
    params: ReaderConnectorRestParams,
    view_name: str,
) -> None:
    payload = _resolve_secret(session, tenant_id, params.secretName)
    auth = _build_auth(payload)
    client = RESTClient(
        base_url=params.baseUrl,
        headers=params.headers or None,
        auth=auth,
        paginator=_build_paginator(params.paginator, params.paginatorConfig),
        data_selector=params.recordsPath,
        session=build_guarded_session(),
    )

    @dlt.resource(name="records", write_disposition="replace")
    def _records():
        yield from client.paginate(params.path, method=params.method, params=params.query or None)

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)


def materialize_postgres_connector(
    conn,
    *,
    session: Session,
    tenant_id: str,
    node_id: str,
    params: ReaderConnectorPostgresParams,
    view_name: str,
) -> None:
    # Défense en profondeur heuristique, pas une garantie (design §5.2) :
    # `params.query` cible Postgres mais est parsée avec le dialecte SQL de
    # DuckDB (même mécanisme que app.pipelines.expr_validation, appliqué ici
    # à un texte SQL complet plutôt qu'à une expression bornée). Vérifié à
    # l'exécution uniquement, jamais à la sauvegarde du pipeline.
    try:
        validate_select_only(parse_ast(conn, params.query))
    except SqlSandboxError as exc:
        raise ConnectorRuntimeError(f"reader.connector.postgres query rejected: {exc}") from exc

    payload = _resolve_secret(session, tenant_id, params.secretName)
    if payload.kind != "postgres_dsn":
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable by reader.connector.postgres "
            "(expected postgres_dsn)"
        )

    @dlt.resource(name="records", write_disposition="replace")
    def _records():
        engine = sa.create_engine(payload.dsn)
        try:
            with engine.connect() as db_conn:
                rows = db_conn.execution_options(yield_per=1000).exec_driver_sql(params.query)
                yield from (dict(row._mapping) for row in rows)
        finally:
            engine.dispose()

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)
