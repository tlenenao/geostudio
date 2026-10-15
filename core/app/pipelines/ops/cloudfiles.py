# SPDX-License-Identifier: Apache-2.0
"""Module de voie D — stockage fichier & SaaS (FME : Dropbox, Box, Google Drive, OneDrive,
SharePoint Online, Azure Files, HDFS/WebHDFS, FTPCaller, ArcGISOnlineConnector, CKANConnector).
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

Un seul patron : `_http_get` = GET/POST gardé (egress SSRF + épinglage DNS via
`app.pipelines.egress`), plafonds d'octets et d'échéance, secret du coffre envoyé UNIQUEMENT aux
URL sous le `baseUrl` auquel il est lié (REV-294), redirections suivies à la main (le secret ne
suit jamais un saut hors portée : un en-tête `api_key` custom survivrait au nettoyage de
`requests`), TLS exigé dès qu'un secret est attaché. Ops :

- `reader.cloudfile` (provider dropbox|box|googledrive|onedrive|sharepoint|azurefiles|hdfs) :
  télécharge UN fichier tabulaire (csv/jsonl/parquet/geojson) puis le matérialise.
- `reader.arcgisonline` : requête paginée d'une couche FeatureServer (f=geojson, jamais esriJSON).
- `reader.ckan` : package_show -> ressource -> fichier (logique de app.harvest.connectors.ckan,
  non importable ici : app.pipelines est sous app.harvest dans le contrat de couches).
- `reader.ftp` / `writer.ftp` : FTPS explicite (TLS + vérification du certificat) seulement.

Écarts FME consignés dans la matrice : lecture d'UN fichier par nœud (pas de listing/suppression/
renommage), SFTP absent
(paramiko = LGPL, interdit), écriture uniquement vers FTPS.

OAuth2 (voie R) : un secret `oauth2_client` (client_credentials ou refresh_token) est échangé
contre un jeton d'accès à l'exécution (`_oauth2_access_token`) — cache mémoire court, jamais
persisté ; un refresh_token renouvelé par le fournisseur est réécrit dans le coffre sous verrou
de ligne, dans une session courte SÉPARÉE (jamais la session du run).

Ne jamais importer contracts/runtime/registries au niveau module (cycle d'import)."""

import base64
import ftplib
import hashlib
import io
import json
import re
import ssl
import time
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import quote, urljoin, urlsplit

import pandas as pd
import requests
import shapely.geometry
import shapely.wkb
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.pipelines import egress
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.operation_contract import OperationContract
from app.sql_ident import quote_ident_duckdb as _qi

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}

MAX_BYTES = 100 * 1024 * 1024
DEADLINE_S = 120.0
_CHUNK = 64 * 1024
_MAX_REDIRECTS = 3
# Les tests passent à False pour parler à un serveur HTTP local ; un test dédié le laisse à True.
_REQUIRE_TLS_FOR_SECRETS = True

_FILE_FORMATS = ("csv", "jsonl", "parquet", "geojson")
FileFormat = Literal["csv", "jsonl", "parquet", "geojson"]
# Taille décompressée admise = facteur x MAX_BYTES (compression colonnaire légitime ~5-10x).
MAX_UNCOMPRESSED_FACTOR = 4
_SECRET_KINDS = ("bearer_token", "api_key", "basic_auth", "oauth2_client")
_TOKEN_MAX_BYTES = 64 * 1024
_TOKEN_DEADLINE_S = 30.0
_TOKEN_CACHE_TTL_S = 300.0
_TOKEN_CACHE_MAX = 256
# (tenant, secret, empreinte des identifiants) -> (jeton d'accès, échéance monotone)
_TOKEN_CACHE: dict[tuple[str, str, str], tuple[str, float]] = {}


def _max_rows() -> int:
    from app.pipelines.connector_runtime import _max_rows as m

    return m()


# --------------------------------------------------------------------------- HTTP gardé


def _resolve_secret(op: str, session, tenant_id, user, name: str | None):
    if not name:
        return None
    from app.pipelines.connector_runtime import PostgresSecretResolver

    try:
        payload = PostgresSecretResolver(session, tenant_id, user).get(name)
    except KeyError:
        raise PipelineRuntimeError(f"{op}: secret '{name}' not found") from None
    if payload.kind not in _SECRET_KINDS:
        raise PipelineRuntimeError(
            f"{op}: secret has kind '{payload.kind}', expected one of {list(_SECRET_KINDS)}"
        )
    if payload.kind == "oauth2_client":
        from app.secrets.schemas import BearerTokenPayload

        token = _oauth2_access_token(op, session, tenant_id, user, name, payload)
        return BearerTokenPayload(token=token, baseUrl=payload.baseUrl)
    return payload


def _token_request(op: str, payload, form: dict[str, str]) -> dict:
    """POST au `tokenUrl` (egress gardé, AUCUNE redirection : le client_secret ne suit jamais
    un saut) -> objet JSON de la réponse, non validé (cf. `_access_from_doc`). Les erreurs
    ne citent jamais le corps de la réponse ni les identifiants."""
    if _REQUIRE_TLS_FOR_SECRETS and urlsplit(payload.tokenUrl).scheme != "https":
        raise PipelineRuntimeError(f"{op}: the OAuth2 tokenUrl must use https")
    data = {**form, "client_id": payload.clientId, "client_secret": payload.clientSecret}
    if payload.scope:
        data["scope"] = payload.scope
    body = _http_get(
        f"{op} (OAuth2 token)",
        payload.tokenUrl,
        method="POST",
        data=data,
        headers={"Accept": "application/json"},
        max_bytes=_TOKEN_MAX_BYTES,
        deadline=time.monotonic() + _TOKEN_DEADLINE_S,
        max_redirects=0,
    )
    try:
        doc = json.loads(body)
    except ValueError as exc:
        raise PipelineRuntimeError(f"{op}: unexpected OAuth2 token answer") from exc
    if not isinstance(doc, dict):
        raise PipelineRuntimeError(f"{op}: unexpected OAuth2 token answer")
    return doc


def _access_from_doc(op: str, doc: dict) -> tuple[str, float]:
    token = doc.get("access_token")
    try:
        ttl = float(doc.get("expires_in") or 3600)
    except (TypeError, ValueError):
        raise PipelineRuntimeError(f"{op}: unexpected OAuth2 token answer") from None
    if not isinstance(token, str) or not token:
        raise PipelineRuntimeError(f"{op}: unexpected OAuth2 token answer")
    if str(doc.get("token_type") or "bearer").lower() != "bearer":
        raise PipelineRuntimeError(f"{op}: OAuth2 token type is not 'bearer'")
    return token, ttl


def _cache_key(tenant_id, name: str, payload) -> tuple[str, str, str]:
    """Empreinte de TOUT ce qui détermine le jeton (refreshToken et baseUrl inclus : un
    secret remplacé ne ressert jamais l'ancien jeton)."""
    parts = (payload.grantType, payload.tokenUrl, payload.clientId, payload.clientSecret,
             payload.scope or "", payload.refreshToken or "", payload.baseUrl or "")  # fmt: skip
    return str(tenant_id), name, hashlib.sha256("\x00".join(parts).encode()).hexdigest()


def _cache_get(key) -> str | None:
    hit = _TOKEN_CACHE.get(key)
    return hit[0] if hit and hit[1] > time.monotonic() else None


def _cache_put(key, token: str, ttl: float) -> None:
    if len(_TOKEN_CACHE) >= _TOKEN_CACHE_MAX:
        _TOKEN_CACHE.clear()  # ponytail: purge totale, LRU si le volume de secrets l'exige
    ttl = min(ttl - 30.0, _TOKEN_CACHE_TTL_S)
    if ttl > 0:
        _TOKEN_CACHE[key] = (token, time.monotonic() + ttl)


def _oauth2_access_token(op: str, session, tenant_id: str, user, name: str, payload) -> str:
    from app.pipelines.ops.operation_contract import IN_PREVIEW

    key = _cache_key(tenant_id, name, payload)
    if (hit := _cache_get(key)) is not None:
        return hit
    if payload.grantType == "client_credentials":
        doc = _token_request(op, payload, {"grant_type": "client_credentials"})
        token, ttl = _access_from_doc(op, doc)
        _cache_put(key, token, ttl)
        return token
    if IN_PREVIEW.get():
        # Un fournisseur peut faire tourner le refresh_token : l'aperçu n'écrit jamais dans
        # le coffre, il ne renouvelle donc pas (jeton déjà en cache seulement).
        raise PipelineRuntimeError(
            f"{op}: preview cannot renew an OAuth2 refresh_token (it may rotate and must be "
            "saved to the vault) — run the pipeline once, then preview within 5 minutes"
        )
    return _refresh_and_rotate(op, session, tenant_id, user, name, payload)


def _refresh_and_rotate(op: str, session, tenant_id: str, user, name: str, payload) -> str:
    """Flux refresh_token sous verrou de la ligne du secret, dans une session courte SÉPARÉE
    (commiter la session du run casserait sa transaction). Sous le verrou : relit la valeur
    courante du coffre (un autre worker a pu la faire tourner) et le cache (il a pu obtenir
    le jeton : un seul appel au fournisseur). Un refresh_token renouvelé est persisté DÈS que
    la réponse JSON est lisible, avant toute autre validation : l'ancien est déjà révoqué."""
    from app.secrets import crypto
    from app.secrets.models import ConnectorSecret
    from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER

    bind = session.get_bind()
    with Session(bind) as locked:
        row = locked.scalar(
            select(ConnectorSecret)
            .where(ConnectorSecret.tenant_id == tenant_id, ConnectorSecret.name == name)
            .with_for_update()
        )
        current = payload
        if row is not None:
            raw = crypto.decrypt(row.ciphertext, row.nonce)
            stored = SECRET_PAYLOAD_ADAPTER.validate_python(raw)
            if stored.kind == "oauth2_client" and stored.clientId == payload.clientId:
                current = stored
        if (hit := _cache_get(_cache_key(tenant_id, name, current))) is not None:
            return hit
        doc = _token_request(
            op, current, {"grant_type": "refresh_token", "refresh_token": current.refreshToken}
        )
        new_refresh = doc.get("refresh_token")
        effective = current
        if isinstance(new_refresh, str) and new_refresh and new_refresh != current.refreshToken:
            effective = current.model_copy(update={"refreshToken": new_refresh})
        try:
            token, ttl = _access_from_doc(op, doc)
        except PipelineRuntimeError as exc:
            token, error = None, exc
        else:
            error = None
            # avant le commit (qui libère le verrou) : le run concurrent trouvera le jeton
            _cache_put(_cache_key(tenant_id, name, effective), token, ttl)
        if effective is not current and row is not None:
            _persist_refresh(op, bind, locked, row, effective, tenant_id, user, name)
    if error is not None:
        raise error
    return token  # type: ignore[return-value]


def _persist_refresh(op, bind, locked, row, effective, tenant_id, user, name) -> None:
    """Réécrit le refresh_token renouvelé ; un échec de commit est rejoué une fois dans une
    session neuve. Perdu malgré tout = compte à ré-autoriser (message explicite)."""
    from app.secrets import crypto
    from app.secrets.models import ConnectorSecret

    def write(s, target) -> None:
        target.ciphertext, target.nonce = crypto.encrypt(effective.model_dump())
        write_audit(
            s,
            tenant_id=tenant_id,
            actor_id=getattr(user, "id", None),
            actor_kind="user" if user is not None else "system",
            action="secret.oauth2_refresh_rotated",
            object_type="secret",
            object_id=target.id,
            payload={"name": name},
        )
        s.commit()

    try:
        write(locked, row)
        return
    except Exception:
        locked.rollback()
    try:
        with Session(bind) as retry:
            target = retry.scalar(
                select(ConnectorSecret).where(
                    ConnectorSecret.tenant_id == tenant_id, ConnectorSecret.name == name
                )
            )
            if target is not None:
                write(retry, target)
                return
    except Exception:
        pass
    raise PipelineRuntimeError(
        f"{op}: the provider renewed the OAuth2 refresh_token but it could not be saved — "
        f"re-authorize the secret '{name}'"
    )


def _credentials(payload, url: str) -> tuple[dict[str, str], dict[str, str]]:
    """(en-têtes, paramètres de requête) du secret POUR CETTE URL ; vides hors portée."""
    from app.pipelines.connector_runtime import _url_within_scope

    if payload is None or not payload.baseUrl or not _url_within_scope(payload.baseUrl, url):
        return {}, {}
    if _REQUIRE_TLS_FOR_SECRETS and urlsplit(url).scheme != "https":
        raise PipelineRuntimeError("a secret is only sent over https")
    if payload.kind == "bearer_token":
        return {"Authorization": f"Bearer {payload.token}"}, {}
    if payload.kind == "basic_auth":
        raw = base64.b64encode(f"{payload.username}:{payload.password}".encode()).decode()
        return {"Authorization": f"Basic {raw}"}, {}
    if payload.location == "header":
        return {payload.key: payload.value}, {}
    return {}, {payload.key: payload.value}


def _http_get(
    op: str,
    url: str,
    *,
    payload=None,
    headers: dict | None = None,
    query: dict | None = None,
    method: str = "GET",
    max_bytes: int | None = None,
    deadline: float | None = None,
    strict_scope: bool = True,
    data: dict | None = None,
    max_redirects: int = _MAX_REDIRECTS,
) -> bytes:
    """Requête gardée -> corps (borné). Un secret doit couvrir l'URL initiale (sinon erreur
    explicite) ; il n'est envoyé qu'aux sauts qui restent sous son `baseUrl`."""
    from app.pipelines.connector_runtime import _url_within_scope

    if (
        strict_scope
        and payload is not None
        and not (payload.baseUrl and _url_within_scope(payload.baseUrl, url))
    ):
        raise PipelineRuntimeError(
            f"{op}: secret baseUrl must cover '{url}' (set it on the secret)"
        )
    max_bytes = max_bytes or MAX_BYTES
    deadline = deadline or time.monotonic() + DEADLINE_S
    session = egress.build_guarded_session()
    try:
        cur, cur_query, cur_method = url, dict(query or {}), method
        for _hop in range(max_redirects + 1):
            cred_h, cred_q = _credentials(payload, cur)
            response = None
            try:
                response = session.request(
                    cur_method,
                    cur,
                    headers={**(headers or {}), **cred_h},
                    params={**cur_query, **cred_q},
                    data=data,
                    stream=True,
                    allow_redirects=False,
                )
                if response.status_code in (301, 302, 303, 307, 308):
                    loc = response.headers.get("Location")
                    if not loc:
                        raise PipelineRuntimeError(f"{op}: redirect without Location")
                    cur, cur_query, data = urljoin(cur, loc), {}, None
                    if response.status_code in (301, 302, 303):
                        cur_method = "GET"
                    continue
                if response.status_code != 200:
                    raise PipelineRuntimeError(f"{op}: server answered HTTP {response.status_code}")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(_CHUNK):
                    total += len(chunk)
                    if total > max_bytes:
                        raise PipelineRuntimeError(f"{op}: response larger than {max_bytes} bytes")
                    if time.monotonic() > deadline:
                        raise PipelineRuntimeError(f"{op}: download exceeded the time limit")
                    chunks.append(chunk)
                return b"".join(chunks)
            finally:
                if response is not None:
                    response.close()
        raise PipelineRuntimeError(f"{op}: too many redirects")
    except egress.EgressBlockedError as exc:
        raise PipelineRuntimeError(f"{op}: egress blocked: {exc}") from exc
    except requests.RequestException as exc:
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, egress.EgressBlockedError):
            raise PipelineRuntimeError(f"{op}: egress blocked: {cause}") from exc
        raise PipelineRuntimeError(f"{op}: request failed: {type(exc).__name__}") from exc
    finally:
        session.close()


# --------------------------------------------------------------------------- matérialisation


def _materialize(conn, frame: pd.DataFrame, view_name: str, op: str) -> None:
    conn.register("_cf_tmp", frame)
    try:
        select = ", ".join(
            f"ST_GeomFromWKB(CAST({_qi(c)} AS BLOB)) AS geometry" if c == "geometry" else _qi(c)
            for c in frame.columns
        )
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT {select} FROM _cf_tmp")
    except Exception as exc:  # types pandas mixtes, etc.
        raise PipelineRuntimeError(f"{op}: cannot load the data ({type(exc).__name__})") from exc
    finally:
        conn.unregister("_cf_tmp")


def _features_frame(features: list, op: str) -> pd.DataFrame:
    rows: list[dict] = []
    for f in features:
        props = {
            k: json.dumps(v) if isinstance(v, (dict, list)) else v
            for k, v in (f.get("properties") or {}).items()
        }
        if any(k.lower() == "geometry" for k in props):
            raise PipelineRuntimeError(f"{op}: a property is named 'geometry' (column collision)")
        geom = f.get("geometry")
        try:
            wkb = shapely.wkb.dumps(shapely.geometry.shape(geom)) if geom else None
        except Exception:
            wkb = None  # géométrie invalide : ligne gardée, géométrie nulle
        rows.append({**props, "geometry": wkb})
    return pd.DataFrame(rows, columns=None if rows else ["geometry"])


def _parse(body: bytes, fmt: str, op: str) -> pd.DataFrame:
    cap = _max_rows()
    try:
        if fmt == "csv":
            frame = pd.read_csv(io.BytesIO(body), nrows=cap + 1)
        elif fmt == "jsonl":
            frame = pd.read_json(io.BytesIO(body), lines=True, nrows=cap + 1)
        elif fmt == "parquet":
            import pyarrow as pa
            import pyarrow.parquet as pq

            pf = pq.ParquetFile(io.BytesIO(body))
            meta = pf.metadata
            if meta.num_rows > cap:
                raise PipelineRuntimeError(f"{op}: plafond de {cap} lignes dépassé")
            # Bombe de décompression : un fichier de quelques Ko peut en valoir des centaines
            # de Mo. Borne sur la taille décompressée DÉCLARÉE (métadonnées), puis sur la taille
            # réelle de chaque row group lu (rattrape des métadonnées mensongères).
            declared = sum(meta.row_group(i).total_byte_size for i in range(meta.num_row_groups))
            if declared > MAX_UNCOMPRESSED_FACTOR * MAX_BYTES:
                raise PipelineRuntimeError(f"{op}: parquet decompresses beyond the size limit")
            tables, total = [], 0
            for i in range(meta.num_row_groups):
                t = pf.read_row_group(i)
                total += t.nbytes
                if total > MAX_UNCOMPRESSED_FACTOR * MAX_BYTES:
                    raise PipelineRuntimeError(f"{op}: parquet decompresses beyond the size limit")
                tables.append(t)
            frame = (
                pa.concat_tables(tables) if tables else pf.schema_arrow.empty_table()
            ).to_pandas()
        else:
            doc = json.loads(body)
            feats = doc["features"]
            if len(feats) > cap:
                raise PipelineRuntimeError(f"{op}: plafond de {cap} lignes dépassé")
            return _features_frame(feats, op)
    except PipelineRuntimeError:
        raise
    except Exception as exc:
        raise PipelineRuntimeError(
            f"{op}: the file is not valid {fmt} ({type(exc).__name__})"
        ) from exc
    if len(frame) > cap:
        raise PipelineRuntimeError(f"{op}: plafond de {cap} lignes dépassé")
    if any(str(c).lower() == "geometry" for c in frame.columns):
        raise PipelineRuntimeError(f"{op}: a column is named 'geometry' (column collision)")
    return frame


# --------------------------------------------------------------------------- reader.cloudfile

Provider = Literal["dropbox", "box", "googledrive", "onedrive", "sharepoint", "azurefiles", "hdfs"]
# Hôtes d'API (surchargés par les tests) ; azurefiles/hdfs/arcgis/ckan portent leur hôte en param.
_API: dict[str, str] = {
    "dropbox": "https://content.dropboxapi.com",
    "box": "https://api.box.com",
    "googledrive": "https://www.googleapis.com",
    "onedrive": "https://graph.microsoft.com",
    "sharepoint": "https://graph.microsoft.com",
}
_ID = re.compile(r"^[A-Za-z0-9_!,.$-]{1,300}$")
_ACCOUNT = re.compile(r"^[a-z0-9]{3,24}$")
_AZ_API_VERSION = "2022-11-02"


def _safe_path(path: str) -> str:
    if not path or "\\" in path or any(ord(c) < 32 for c in path) or ".." in path.split("/"):
        raise ValueError("path: invalid (control character, backslash or '..' segment)")
    return path.strip("/")


class ReaderCloudFileParams(BaseModel):
    """Lit un fichier tabulaire (CSV, JSON Lines, Parquet ou GeoJSON) stocké chez un fournisseur
    de fichiers : Dropbox, Box, Google Drive, OneDrive, SharePoint Online, Azure Files ou HDFS
    (WebHDFS). `secretName` référence un secret oauth2_client (jeton renouvelé à chaque
    exécution : Dropbox, Box, OneDrive, SharePoint, Azure AD pour Azure Files), bearer_token,
    api_key ou basic_auth lié (`baseUrl`) à l'API du fournisseur ; `file` = chemin (Dropbox,
    Azure Files, HDFS) ou identifiant (Box, Drive, OneDrive, SharePoint)."""

    provider: Provider
    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    file: str = Field(..., min_length=1, max_length=500)
    format: FileFormat = "csv"
    driveId: str | None = Field(
        None, description="OneDrive : lecteur partagé (sinon « mon OneDrive »)"
    )
    siteId: str | None = Field(None, description="SharePoint : identifiant du site Graph")
    account: str | None = Field(None, description="Azure Files : compte de stockage")
    share: str | None = Field(None, description="Azure Files : nom du partage")
    baseUrl: str | None = Field(
        None, description="HDFS : URL WebHDFS du namenode, https://hôte:port"
    )

    @model_validator(mode="after")
    def _check(self):
        p = self.provider
        if p in ("dropbox", "azurefiles", "hdfs"):
            _safe_path(self.file)
        elif not _ID.match(self.file):
            raise ValueError("file: identifiant invalide")
        for field in (self.driveId, self.siteId):
            if field is not None and not _ID.match(field):
                raise ValueError("driveId/siteId: identifiant invalide")
        if p == "sharepoint" and not self.siteId:
            raise ValueError("siteId requis pour sharepoint")
        if p == "azurefiles":
            if not (self.account and _ACCOUNT.match(self.account) and self.share):
                raise ValueError("account (a-z0-9, 3-24) et share requis pour azurefiles")
            _safe_path(self.share)
        if p == "hdfs":
            if not self.baseUrl or urlsplit(self.baseUrl).scheme not in ("http", "https"):
                raise ValueError("baseUrl http(s) requis pour hdfs")
        return self


def _cloudfile_request(p: ReaderCloudFileParams) -> dict[str, Any]:
    q = lambda s: quote(s, safe="/")  # noqa: E731
    match p.provider:
        case "dropbox":
            return {
                "method": "POST",
                "url": f"{_API['dropbox']}/2/files/download",
                "headers": {"Dropbox-API-Arg": json.dumps({"path": "/" + p.file.strip("/")})},
            }
        case "box":
            return {"url": f"{_API['box']}/2.0/files/{quote(p.file)}/content"}
        case "googledrive":
            return {
                "url": f"{_API['googledrive']}/drive/v3/files/{quote(p.file)}",
                "query": {"alt": "media", "supportsAllDrives": "true"},
            }
        case "onedrive":
            root = f"drives/{quote(p.driveId)}" if p.driveId else "me/drive"
            return {"url": f"{_API['onedrive']}/v1.0/{root}/items/{quote(p.file)}/content"}
        case "sharepoint":
            return {
                "url": f"{_API['sharepoint']}/v1.0/sites/{quote(p.siteId or '')}"
                f"/drive/items/{quote(p.file)}/content"
            }
        case "azurefiles":
            return {
                "url": f"https://{p.account}.file.core.windows.net/{q(p.share or '')}/{q(p.file)}",
                "headers": {
                    "x-ms-version": _AZ_API_VERSION,
                    "x-ms-file-request-intent": "backup",
                },
            }
        case _:  # hdfs
            return {
                "url": f"{(p.baseUrl or '').rstrip('/')}/webhdfs/v1/{q(p.file)}",
                "query": {"op": "OPEN"},
            }


def read_cloudfile(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    op = "reader.cloudfile"
    p = ReaderCloudFileParams.model_validate(params)
    payload = _resolve_secret(op, session, tenant_id, user, p.secretName)
    body = _http_get(op, payload=payload, **_cloudfile_request(p))
    _materialize(conn, _parse(body, p.format, op), view_name, op)
    return 4326


READERS["reader.cloudfile"] = read_cloudfile
CONTRACTS.append(
    OperationContract(
        op="reader.cloudfile",
        kind="reader",
        params_schema=ReaderCloudFileParams,
        engine="python",
        engine_license="MIT (DuckDB) ; HTTP via requests (Apache-2.0)",
    )
)


# --------------------------------------------------------------------------- reader.arcgisonline

_ARCGIS_PAGE = 1000


class ReaderArcgisOnlineParams(BaseModel):
    """Lit les entités d'une couche ArcGIS Online / Enterprise (FeatureServer ou MapServer,
    requête paginée, sortie GeoJSON en WGS84) : URL de la couche, filtre `where`, plafond
    d'entités. `secretName` (facultatif, couches publiques) = secret api_key (jeton en paramètre
    d'URL) ou bearer_token lié à l'hôte de la couche."""

    layerUrl: str = Field(..., min_length=1, description="https://…/FeatureServer/0")
    secretName: str | None = Field(None, json_schema_extra={"format": "secret-name"})
    where: str = Field("1=1", max_length=2000)
    outFields: str = Field("*", max_length=2000)
    maxFeatures: int = Field(10_000, ge=1, le=100_000)

    @model_validator(mode="after")
    def _check(self):
        parts = urlsplit(self.layerUrl)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.query:
            raise ValueError("layerUrl: https://hôte/…/FeatureServer/<n> attendu, sans requête")
        return self


def read_arcgisonline(
    conn, *, session, tenant_id, node_id, params, view_name, user, base_uri
) -> int:
    op = "reader.arcgisonline"
    p = ReaderArcgisOnlineParams.model_validate(params)
    payload = _resolve_secret(op, session, tenant_id, user, p.secretName)
    url = p.layerUrl.rstrip("/") + "/query"
    from app.pipelines.connector_runtime import _max_pages

    features: list = []
    want = min(p.maxFeatures, _max_rows())
    budget, pages = MAX_BYTES, 0
    deadline = time.monotonic() + DEADLINE_S
    while len(features) < want:
        pages += 1
        if pages > _max_pages():
            raise PipelineRuntimeError(f"{op}: page limit exceeded")
        page = min(_ARCGIS_PAGE, want - len(features))
        body = _http_get(
            op,
            url,
            payload=payload,
            max_bytes=budget,
            deadline=deadline,
            query={
                "where": p.where,
                "outFields": p.outFields,
                "f": "geojson",
                "outSR": "4326",
                "returnGeometry": "true",
                "resultOffset": str(len(features)),
                "resultRecordCount": str(page),
            },
        )
        budget -= len(body)  # budget d'octets cumulé sur l'ensemble des pages
        try:
            doc = json.loads(body)
        except ValueError as exc:
            raise PipelineRuntimeError(f"{op}: answer is not JSON") from exc
        if isinstance(doc, dict) and "error" in doc:  # ArcGIS répond 200 + {"error": ...}
            err = doc["error"]
            code = err.get("code", "?") if isinstance(err, dict) else "?"
            raise PipelineRuntimeError(f"{op}: service error {code}")
        batch = doc.get("features") if isinstance(doc, dict) else None
        if not isinstance(batch, list):
            raise PipelineRuntimeError(f"{op}: answer is not a GeoJSON FeatureCollection")
        features += batch
        props = doc.get("properties")
        more = doc.get("exceededTransferLimit") or (
            isinstance(props, dict) and props.get("exceededTransferLimit")
        )
        if not batch or not more:
            break
    try:
        frame = _features_frame(features[:want], op)
    except PipelineRuntimeError:
        raise
    except Exception as exc:  # feature / properties qui ne sont pas des objets
        raise PipelineRuntimeError(f"{op}: malformed feature ({type(exc).__name__})") from exc
    _materialize(conn, frame, view_name, op)
    return 4326


READERS["reader.arcgisonline"] = read_arcgisonline
CONTRACTS.append(
    OperationContract(
        op="reader.arcgisonline",
        kind="reader",
        params_schema=ReaderArcgisOnlineParams,
        engine="python",
        engine_license="MIT (DuckDB) ; API REST Esri (publique) via requests (Apache-2.0)",
    )
)


# --------------------------------------------------------------------------- reader.ckan

_CKAN_FORMATS = {"CSV": "csv", "GEOJSON": "geojson", "PARQUET": "parquet", "JSONL": "jsonl"}


class ReaderCkanParams(BaseModel):
    """Lit une ressource tabulaire (CSV, GeoJSON, Parquet, JSON Lines) d'un jeu de données d'un
    portail CKAN (data.gouv.fr hébergé sur CKAN, etc.) : adresse du portail, identifiant ou nom
    du jeu, identifiant de ressource (sinon la première ressource lisible). `secretName`
    (facultatif, jeux privés) est lié à l'hôte du portail."""

    baseUrl: str = Field(..., min_length=1, description="https://portail.example")
    datasetId: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,200}$")
    resourceId: str | None = Field(None, pattern=r"^[A-Za-z0-9_.:-]{1,200}$")
    secretName: str | None = Field(None, json_schema_extra={"format": "secret-name"})

    @model_validator(mode="after")
    def _check(self):
        parts = urlsplit(self.baseUrl)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.query:
            raise ValueError("baseUrl: https://hôte[/préfixe] attendu")
        return self


def read_ckan(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    op = "reader.ckan"
    p = ReaderCkanParams.model_validate(params)
    payload = _resolve_secret(op, session, tenant_id, user, p.secretName)
    api = p.baseUrl.rstrip("/") + "/api/3/action/package_show"
    try:
        doc = json.loads(_http_get(op, api, payload=payload, query={"id": p.datasetId}))
        resources = doc["result"]["resources"]
    except PipelineRuntimeError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise PipelineRuntimeError(f"{op}: unexpected package_show answer") from exc
    candidates = [
        (r, _CKAN_FORMATS.get(str(r.get("format", "")).upper()))
        for r in resources
        if isinstance(r, dict) and (p.resourceId is None or r.get("id") == p.resourceId)
    ]
    candidates = [(r, f) for r, f in candidates if f and r.get("url")]
    if not candidates:
        raise PipelineRuntimeError(f"{op}: no readable resource (csv/geojson/parquet/jsonl) found")
    resource, fmt = candidates[0]
    # URL de ressource arbitraire (autre hôte possible) : le secret n'y est jamais envoyé,
    # sauf si elle reste sous son baseUrl (`_credentials`) ; egress gardé comme le reste.
    body = _http_get(op, str(resource["url"]), payload=payload, strict_scope=False)
    _materialize(conn, _parse(body, str(fmt), op), view_name, op)
    return 4326


READERS["reader.ckan"] = read_ckan
CONTRACTS.append(
    OperationContract(
        op="reader.ckan",
        kind="reader",
        params_schema=ReaderCkanParams,
        engine="python",
        engine_license=(
            "MIT (DuckDB) ; API Action CKAN (JSON REST) via requests (Apache-2.0) — "
            "le serveur CKAN (AGPL-3.0) n'est pas lié, simple appel client"
        ),
    )
)


# --------------------------------------------------------------------------- FTPS (FTPCaller)

_FTP_TIMEOUT_S = 30


class _FtpTarget(BaseModel):
    host: str = Field(..., pattern=r"^[A-Za-z0-9.-]{1,253}$")
    port: int = Field(21, ge=1, le=65535)
    path: str = Field(..., min_length=1, max_length=500)
    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})

    @model_validator(mode="after")
    def _path(self):
        if (
            self.path.startswith("-")
            or any(ord(c) < 32 for c in self.path)
            or ".." in self.path.split("/")
        ):
            # CR/LF = injection de commande FTP ; `-` initial = option de certains serveurs
            raise ValueError("path: invalid (control character, leading '-' or '..' segment)")
        return self


class ReaderFtpParams(_FtpTarget):
    """Lit un fichier tabulaire (CSV, JSON Lines, Parquet ou GeoJSON) sur un serveur FTPS (FTP
    sur TLS explicite, certificat vérifié ; le FTP en clair et SFTP ne sont pas pris en charge).
    `secretName` = secret basic_auth dont le `baseUrl` (https://<hôte>) désigne l'hôte du
    serveur : le secret n'est jamais envoyé à un autre hôte."""

    format: FileFormat = "csv"


class WriterFtpParams(_FtpTarget):
    """Dépose les lignes reçues dans un fichier d'un serveur FTPS (CSV, JSON Lines ou Parquet ;
    FTP sur TLS explicite, certificat vérifié). Le fichier cible est remplacé à chaque exécution
    (rejeu idempotent). Les colonnes géométrie ne sont pas prises en charge. `secretName` =
    secret basic_auth dont le `baseUrl` (https://<hôte>) désigne l'hôte du serveur."""

    format: Literal["csv", "jsonl", "parquet"] = "csv"


def _ftps_connect(op: str, p: _FtpTarget, payload) -> ftplib.FTP_TLS:
    """Connexion FTPS épinglée sur l'IP validée par la garde d'egress ; le nom d'hôte d'origine
    reste utilisé pour SNI et vérification du certificat. Mode passif : ftplib ignore l'adresse
    annoncée par le serveur (trust_server_pasv_ipv4_address=False) et réutilise celle du canal
    de contrôle, donc le canal de données reste épinglé lui aussi."""
    if payload.kind != "basic_auth":
        raise PipelineRuntimeError(f"{op}: secret has kind '{payload.kind}', expected basic_auth")
    bound = urlsplit(payload.baseUrl or "")
    # Hôte ET port : un port explicite du baseUrl doit être celui du nœud (sinon 21 par défaut).
    if (bound.hostname or "").lower() != p.host.lower() or (
        bound.port is not None and bound.port != p.port
    ):
        raise PipelineRuntimeError(f"{op}: secret baseUrl host/port must be '{p.host}:{p.port}'")
    try:
        ip = egress.assert_egress_allowed(f"http://{p.host}")
    except egress.EgressBlockedError as exc:
        raise PipelineRuntimeError(f"{op}: egress blocked: {exc}") from exc
    ctx = ssl.create_default_context()
    ftp = ftplib.FTP_TLS(context=ctx, timeout=_FTP_TIMEOUT_S)
    try:
        ftp.connect(str(ip) if ip else p.host, p.port)
        ftp.host = p.host  # SNI + hostname check
        ftp.login(payload.username, payload.password)  # AUTH TLS avant les identifiants
        ftp.prot_p()
    except (OSError, ftplib.Error, ssl.SSLError) as exc:
        ftp.close()
        raise PipelineRuntimeError(f"{op}: FTPS connection failed ({type(exc).__name__})") from exc
    return ftp


def read_ftp(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    op = "reader.ftp"
    p = ReaderFtpParams.model_validate(params)
    payload = _resolve_secret(op, session, tenant_id, user, p.secretName)
    ftp = _ftps_connect(op, p, payload)
    buf = bytearray()
    deadline = time.monotonic() + DEADLINE_S

    # ponytail: échéance vérifiée entre blocs ; un serveur au goutte-à-goutte dépasse jusqu'au
    # délai de lecture du socket (_FTP_TIMEOUT_S) par bloc.
    def sink(chunk: bytes) -> None:
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            raise PipelineRuntimeError(f"{op}: file larger than {MAX_BYTES} bytes")
        if time.monotonic() > deadline:
            raise PipelineRuntimeError(f"{op}: download exceeded the time limit")

    try:
        ftp.retrbinary(f"RETR {p.path}", sink)
    except (OSError, ftplib.Error) as exc:
        raise PipelineRuntimeError(f"{op}: transfer failed ({type(exc).__name__})") from exc
    finally:
        ftp.close()
    _materialize(conn, _parse(bytes(buf), p.format, op), view_name, op)
    return 4326


def _serialize(frame: pd.DataFrame, fmt: str) -> bytes:
    out = io.BytesIO()
    if fmt == "csv":
        out.write(frame.to_csv(index=False).encode())
    elif fmt == "jsonl":
        out.write(frame.to_json(orient="records", lines=True, date_format="iso").encode())
    else:
        frame.to_parquet(out, index=False)
    return out.getvalue()


def write_ftp(
    session,
    conn,
    *,
    node,
    view_by_node: dict,
    tenant_id: str,
    user,
    should_cancel: Callable[[], bool] | None = None,
    **_extra: Any,
):
    from app.pipelines.runtime import NodeStat

    op = node.op
    p = WriterFtpParams.model_validate(node.params)
    payload = _resolve_secret(op, session, tenant_id, user, p.secretName)
    view = view_by_node[node.id]
    desc = conn.execute(f"SELECT * FROM {_qi(view)} LIMIT 0").description
    if any(d[1].id == "geometry" for d in desc):
        raise PipelineRuntimeError(f"{op}: geometry columns are not supported")
    limit = _max_rows()
    frame = conn.execute(f"SELECT * FROM {_qi(view)} LIMIT {limit + 1}").df()
    if len(frame) > limit:
        raise PipelineRuntimeError(f"{op}: plafond de {limit} lignes dépassé")
    data = _serialize(frame, p.format)
    if len(data) > MAX_BYTES:
        raise PipelineRuntimeError(f"{op}: output larger than {MAX_BYTES} bytes")
    if should_cancel is not None and should_cancel():
        raise PipelineRuntimeError(f"{op}: cancelled")
    # Audit AVANT l'effet distant (irréversible), dans une session courte SÉPARÉE : commiter
    # `session` casserait la transaction du run.
    with Session(session.get_bind()) as audit_session:
        write_audit(
            audit_session,
            tenant_id=tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="pipeline.external_write",
            object_type="connector_secret",
            object_id=p.secretName,
            payload={"op": op, "host": p.host, "path": p.path, "rows": len(frame)},
        )
        audit_session.commit()
    ftp = _ftps_connect(op, p, payload)
    try:
        # Fichier temporaire puis RNFR/RNTO : un transfert interrompu ne tronque pas l'ancien.
        tmp = f"{p.path}.part"
        try:
            ftp.storbinary(f"STOR {tmp}", io.BytesIO(data))
            try:
                ftp.rename(tmp, p.path)
            except ftplib.error_perm:  # destination existante refusée par certains serveurs
                ftp.delete(p.path)
                ftp.rename(tmp, p.path)
        except (OSError, ftplib.Error):
            try:
                ftp.delete(tmp)
            except (OSError, ftplib.Error):
                pass
            raise
    except (OSError, ftplib.Error) as exc:
        raise PipelineRuntimeError(f"{op}: transfer failed ({type(exc).__name__})") from exc
    finally:
        ftp.close()
    return NodeStat(node.id, op, len(frame), {"bytes": len(data)})


READERS["reader.ftp"] = read_ftp
WRITERS["writer.ftp"] = write_ftp
for _op, _kind, _model in (
    ("reader.ftp", "reader", ReaderFtpParams),
    ("writer.ftp", "writer", WriterFtpParams),
):
    CONTRACTS.append(
        OperationContract(
            op=_op,
            kind=_kind,  # type: ignore[arg-type]
            params_schema=_model,
            engine="python",
            engine_license="MIT (DuckDB) ; ftplib/ssl (PSF, stdlib)",
        )
    )
