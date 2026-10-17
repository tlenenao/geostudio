# SPDX-License-Identifier: Apache-2.0
"""Module de voie R — ops qui exigent un nouveau kind de secret (`mongodb_uri`).
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

- `reader.mongodb` (FME MongoDB, lecture) : `find()` borné sur une collection externe via
  pymongo (Apache-2.0). Sécurité :
  * l'URI du coffre n'est JAMAIS passée telle quelle à `MongoClient` : seuls l'hôte, les
    identifiants, la base, `authSource` et `authMechanism` (SCRAM seulement — MONGODB-AWS/OIDC
    interrogeraient un point de métadonnées interne) en sont retenus ; TLS forcé, vérification
    du certificat et du nom d'hôte jamais désactivable (une URI qui le demande est refusée) ;
  * `directConnection=True` sur UN nœud validé par la garde d'egress : pas de découverte de
    topologie, donc un serveur hostile ne peut pas faire contacter des membres « annoncés »
    internes ; `mongodb+srv` est résolu par pymongo (règle de suffixe de domaine SRV du
    standard) puis seul le 1er nœud est contacté ;
  * épinglage DNS : pymongo n'offre ni `hostaddr` ni résolveur injectable. Résidu TOCTOU
    (rebinding entre la garde et la connexion) assumé comme Oracle `tcps` (cf.
    `egress.pin_dsn_host`) : le TLS vérifié exige un certificat valide pour le nom contrôlé,
    qu'un service interne ciblé par rebinding ne présente pas ;
  * plafonds : documents (`maxDocuments`, plafond plateforme de lignes), octets BSON cumulés,
    échéance client + `maxTimeMS` serveur, nombre de colonnes aplaties.
  Aplatissement : sous-documents en colonnes `a.b` (profondeur 5), tableaux en JSON, ObjectId
  en texte, dates en TIMESTAMP ; une colonne aux types mêlés passe en texte ; erreur par ligne
  dans la colonne `_error` (collision de noms, géométrie invalide) au lieu d'échouer le run.

Ne jamais importer contracts/runtime/registries au niveau module (cycle d'import)."""

import base64
import datetime as dt
import json
import time
from collections.abc import Callable
from typing import Any

import pandas as pd
import shapely.geometry
import shapely.wkb
from pydantic import BaseModel, Field, field_validator

from app.pipelines import egress
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.operation_contract import OperationContract

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}

MAX_BYTES = 100 * 1024 * 1024
DEADLINE_S = 120.0
MAX_COLUMNS = 2000
_MAX_DEPTH = 5
_TIMEOUT_MS = 10_000
_SCRAM = {"SCRAM-SHA-1", "SCRAM-SHA-256", "DEFAULT"}
_TLS_OFF = ("tlsInsecure", "tlsAllowInvalidCertificates", "tlsAllowInvalidHostnames")
_FORBIDDEN_FILTER_OPS = {"$where", "$function", "$accumulator"}
_FIELD = r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,200}$"


_MAX_FILTER_DEPTH = 32


def _check_filter(node: Any, depth: int = 0) -> None:
    if depth > _MAX_FILTER_DEPTH:  # borne explicite : jamais de RecursionError (500)
        raise ValueError(f"filter: nested deeper than {_MAX_FILTER_DEPTH} levels")
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _FORBIDDEN_FILTER_OPS:
                raise ValueError(f"filter: operator {k} (server-side JavaScript) is not allowed")
            _check_filter(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _check_filter(v, depth + 1)


class ReaderMongoDbParams(BaseModel):
    """Lit les documents d'une collection MongoDB externe (filtre, projection, plafond de
    documents) et les aplatit en colonnes : sous-documents en colonnes `a.b`, tableaux en
    JSON, ObjectId en texte, dates typées, erreurs par document dans `_error`. `secretName` =
    secret mongodb_uri ; TLS toujours exigé. `geometryField` (facultatif) désigne un champ
    GeoJSON converti en géométrie (WGS84)."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    database: str | None = Field(
        None, pattern=r'^[^/\\. "$\x00]{1,64}$', description="sinon la base de l'URI"
    )
    collection: str = Field(..., pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,119}$")
    filter: dict[str, Any] = Field(default_factory=dict, description="filtre find() en JSON")
    projection: list[str] | None = Field(None, max_length=200)
    geometryField: str | None = Field(
        None, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,200}$", description="champ de 1er niveau"
    )
    maxDocuments: int = Field(10_000, ge=1, le=1_000_000)

    @field_validator("collection")
    @classmethod
    def _not_system(cls, v: str) -> str:
        if v.startswith("system."):
            raise ValueError("collection: system collections are not readable")
        return v

    @field_validator("filter")
    @classmethod
    def _filter(cls, v: dict[str, Any]) -> dict[str, Any]:
        _check_filter(v)
        return v

    @field_validator("projection")
    @classmethod
    def _projection(cls, v: list[str] | None) -> list[str] | None:
        import re

        if v is not None and not all(re.match(_FIELD, f) for f in v):
            raise ValueError("projection: invalid field name")
        return v


def _max_rows() -> int:
    from app.pipelines.connector_runtime import _max_rows as m

    return m()


def _resolve_uri(op: str, session, tenant_id, user, name: str) -> str:
    from app.pipelines.connector_runtime import PostgresSecretResolver

    try:
        payload = PostgresSecretResolver(session, tenant_id, user).get(name)
    except KeyError:
        raise PipelineRuntimeError(f"{op}: secret '{name}' not found") from None
    if payload.kind != "mongodb_uri":
        raise PipelineRuntimeError(f"{op}: secret has kind '{payload.kind}', expected mongodb_uri")
    return payload.uri


def _client_kwargs(op: str, uri: str) -> tuple[dict[str, Any], str | None]:
    """URI -> (kwargs MongoClient sûrs, base par défaut). Les erreurs ne citent jamais l'URI
    (elle porte le mot de passe)."""
    from pymongo.uri_parser import parse_uri

    try:
        parsed = parse_uri(uri, connect_timeout=_TIMEOUT_MS / 1000)
    except Exception as exc:  # InvalidURI, ConfigurationError, échec SRV : messages non sûrs
        raise PipelineRuntimeError(f"{op}: invalid MongoDB URI ({type(exc).__name__})") from None
    opts = parsed["options"]
    if opts.get("tls") is False or opts.get("ssl") is False or any(opts.get(o) for o in _TLS_OFF):
        raise PipelineRuntimeError(f"{op}: TLS with certificate verification is required")
    mechanism = opts.get("authMechanism")
    if mechanism and mechanism not in _SCRAM:
        raise PipelineRuntimeError(f"{op}: authMechanism must be SCRAM-SHA-1 or SCRAM-SHA-256")
    host, port = parsed["nodelist"][0]
    if not host or host.startswith("/") or host.endswith(".sock"):
        raise PipelineRuntimeError(f"{op}: a network host is required")
    try:
        egress.assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")
    except egress.EgressBlockedError as exc:
        raise PipelineRuntimeError(f"{op}: egress blocked: {exc}") from exc
    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "directConnection": True,
        "tls": True,
        "serverSelectionTimeoutMS": _TIMEOUT_MS,
        "connectTimeoutMS": _TIMEOUT_MS,
        "socketTimeoutMS": int(DEADLINE_S * 1000),
        "appname": "geostudio-pipeline",
    }
    if parsed["username"]:
        kwargs["username"] = parsed["username"]
        kwargs["password"] = parsed["password"]
        kwargs["authSource"] = opts.get("authSource") or parsed["database"] or "admin"
        if mechanism and mechanism != "DEFAULT":
            kwargs["authMechanism"] = mechanism
    return kwargs, parsed["database"]


def _scalar(value: Any) -> Any:
    from bson import Binary, Decimal128, ObjectId

    if value is None or isinstance(value, (bool, int, float, str, dt.datetime)):
        return value
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (bytes, Binary)):
        return base64.b64encode(bytes(value)).decode()
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str, ensure_ascii=False)
    return str(value)  # Regex, Timestamp, Code, MinKey…


def _flatten(doc: dict, out: dict, prefix: str = "", depth: int = 0) -> None:
    for key, value in doc.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict) and value and depth < _MAX_DEPTH:
            _flatten(value, out, name + ".", depth + 1)
            continue
        if name in out:
            raise ValueError(f"column '{name}' appears twice after flattening")
        out[name] = _scalar(value)


def _row(doc: dict, geometry_field: str | None) -> dict:
    """Un document -> une ligne ; une erreur reste sur cette ligne (`_error`) : géométrie
    invalide = géométrie nulle, collision de noms = ligne réduite à `_id`."""
    doc = dict(doc)
    geom = doc.pop(geometry_field, None) if geometry_field is not None else None
    row: dict = {}
    error = None
    try:
        _flatten(doc, row)
        reserved = {"_error", "geometry"} if geometry_field is not None else {"_error"}
        if any(k.lower() in reserved for k in row):  # DuckDB : identifiants insensibles à la casse
            raise ValueError("a field collides with a reserved column (_error/geometry)")
    except ValueError as exc:
        row, error = {"_id": _scalar(doc.get("_id"))}, str(exc)
    if geometry_field is not None:
        row["geometry"] = None
        if geom is not None:
            try:
                row["geometry"] = shapely.wkb.dumps(shapely.geometry.shape(geom))
            except Exception:
                error = error or f"field '{geometry_field}' is not valid GeoJSON"
    row["_error"] = error
    return row


def _missing(v: Any) -> bool:
    return v is None or (pd.api.types.is_scalar(v) and bool(pd.isna(v)))  # None/NaN/NaT


def _frame(rows: list[dict], op: str, geometry_field: str | None) -> pd.DataFrame:
    columns: dict[str, None] = {}
    for r in rows:
        columns.update(dict.fromkeys(r))
        if len(columns) > MAX_COLUMNS:
            raise PipelineRuntimeError(f"{op}: more than {MAX_COLUMNS} columns after flattening")
    if geometry_field is None and any(c.lower() == "geometry" for c in columns):
        raise PipelineRuntimeError(
            f"{op}: a field is named 'geometry' (column collision) — set geometryField"
        )
    columns.setdefault("_error", None)
    frame = pd.DataFrame(rows, columns=list(columns))
    for col in frame.columns:
        if col == "geometry":
            continue
        kinds = {
            "num" if isinstance(v, (int, float)) and not isinstance(v, bool) else type(v)
            for v in frame[col]
            if not _missing(v)
        }
        if len(kinds) > 1:  # types mêlés d'un document à l'autre : texte
            frame[col] = frame[col].map(lambda v: None if _missing(v) else str(v))
    return frame


def read_mongodb(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    op = "reader.mongodb"
    p = ReaderMongoDbParams.model_validate(params)
    kwargs, uri_db = _client_kwargs(op, _resolve_uri(op, session, tenant_id, user, p.secretName))
    database = p.database or uri_db
    if not database:
        raise PipelineRuntimeError(f"{op}: no database (set it in the node or the URI)")
    from bson import decode, json_util
    from bson.raw_bson import RawBSONDocument
    from pymongo.errors import PyMongoError

    cap = _max_rows()
    want = min(p.maxDocuments, cap)
    deadline = time.monotonic() + DEADLINE_S
    rows: list[dict] = []
    total = 0
    client = None
    # AUD-081 : Extended JSON ({"$oid": ..}, {"$date": ..}) -> types BSON ; sans cela un
    # filtre sur _id ou une date ne correspond à rien. _check_filter a validé le JSON brut.
    flt = json_util.loads(json.dumps(p.filter))
    try:
        client = MongoClient(document_class=RawBSONDocument, **kwargs)
        cursor = client[database][p.collection].find(
            flt,
            projection=dict.fromkeys(p.projection, 1) if p.projection else None,
            limit=want + 1,
            max_time_ms=int(DEADLINE_S * 1000),
            batch_size=1000,
        )
        for raw in cursor:
            if len(rows) == want:
                if want == cap and p.maxDocuments > cap:
                    raise PipelineRuntimeError(f"{op}: plafond de {cap} lignes dépassé")
                break  # limite demandée par l'auteur (maxDocuments)
            total += len(raw.raw)
            if total > MAX_BYTES:
                raise PipelineRuntimeError(f"{op}: documents larger than {MAX_BYTES} bytes")
            if time.monotonic() > deadline:
                raise PipelineRuntimeError(f"{op}: read exceeded the time limit")
            rows.append(_row(decode(raw.raw), p.geometryField))
    except PyMongoError as exc:
        raise PipelineRuntimeError(f"{op}: MongoDB error ({type(exc).__name__})") from None
    finally:
        if client is not None:
            client.close()
    from app.pipelines.ops.cloudfiles import _materialize

    _materialize(conn, _frame(rows, op, p.geometryField), view_name, op)
    return 4326


def MongoClient(**kwargs):  # noqa: N802 — seam de test (remplacé par un faux client)
    from pymongo import MongoClient as _Client

    return _Client(**kwargs)


READERS["reader.mongodb"] = read_mongodb
CONTRACTS.append(
    OperationContract(
        op="reader.mongodb",
        kind="reader",
        params_schema=ReaderMongoDbParams,
        engine="python",
        engine_license="MIT (DuckDB) ; pymongo (Apache-2.0) + dnspython (ISC)",
    )
)
