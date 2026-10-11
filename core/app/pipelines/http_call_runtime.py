# SPDX-License-Identifier: Apache-2.0
"""`transform.httpCall` (HTTPCaller FME) — un appel HTTP par ligne d'entrée.

Design docs/superpowers/specs/2026-09-21-transform-http-call-design.md. Matérialise `view_name`
(mécanisme `OperationContract.execute`, jamais `compiler.py`). Les expressions SQL bornées sont
évaluées UNE fois dans une table de staging (colonne `__rn`) ; les threads réseau ne touchent
jamais la connexion DuckDB ; les résultats sont rejoints sur `__rn`, donc les colonnes d'entrée
(géométrie comprise) ne repassent jamais par Python. Imports lourds (dlt, egress) différés
dans les fonctions : `contracts.py` importe ce module au chargement."""

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pandas as pd
import requests

from app.pipelines.errors import PipelineRuntimeError
from app.sql_ident import quote_ident_duckdb as _qi

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER_S = 60.0
_PREVIEW_MAX_CALLS = 20
_ERR_BODY_CHARS = 2000
_INTERNAL = ("__rn", "__http_url", "__http_headers", "__http_body")


class _RowError(Exception):
    """Ligne inexploitable (non retentée) : devient `httpStatus="error"` sur cette ligne."""


@dataclass
class _Outcome:
    code: int | None = None
    body: str | None = None
    error: str | None = None
    retryable: bool = False
    retry_after: float | None = None
    skipped: bool = False

    @property
    def status(self) -> str:
        return "skipped" if self.skipped else ("error" if self.error else "success")


def _max_rows() -> int:
    from app.pipelines import connector_runtime as cr

    return cr._env_int("CORE_PIPELINES_HTTP_CALL_MAX_ROWS", 10_000)


def _parse_retry_after(raw: str | None) -> float | None:
    # ponytail: secondes seulement (pas la forme HTTP-date) ; ajouter si un service l'exige.
    try:
        return max(0.0, float(raw)) if raw is not None else None
    except ValueError:
        return None


def _classify(code: int, body: str, headers, *, follows_redirects: bool) -> _Outcome:
    if code in _RETRYABLE_STATUS:
        return _Outcome(
            code,
            body,
            error=f"HTTP {code}",
            retryable=True,
            retry_after=_parse_retry_after(headers.get("Retry-After")),
        )
    if code >= 400:
        return _Outcome(code, body, error=f"HTTP {code}")
    if 300 <= code < 400 and not follows_redirects:
        return _Outcome(code, body, error="redirection non suivie")
    return _Outcome(code, body)


def _delay(p, attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(retry_after, _MAX_RETRY_AFTER_S)
    return p.initialBackoffSeconds * (2**attempt)


def _run_with_retry(p, attempt: Callable[[], _Outcome]) -> _Outcome:
    """Retry maison (pas urllib3.Retry : backoff urllib3 2.x sans délai avant le 1er retry) ;
    la garde d'egress s'applique ainsi à chaque tentative. Retry sur délai/connexion et sur
    429/5xx ; délai = `Retry-After` (plafonné) sinon `initialBackoffSeconds * 2**n`."""
    from app.pipelines import connector_runtime as cr

    for n in range(p.maxRetries + 1):
        try:
            out = attempt()
        except _RowError as exc:
            return _Outcome(error=str(exc))
        except requests.HTTPError as exc:  # chemin paginé : dlt lève sur >= 400 (Task 5)
            resp = exc.response
            if resp is None:
                return _Outcome(error="HTTPError")
            out = _classify(
                resp.status_code, resp.text[:_ERR_BODY_CHARS], resp.headers, follows_redirects=True
            )
        except Exception as exc:  # noqa: BLE001 — toute erreur réseau devient une erreur de ligne
            blocked = cr._find_egress_blocked_cause(exc)
            if blocked is not None:
                return _Outcome(error="egress refusé")
            if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
                out = _Outcome(error=type(exc).__name__, retryable=True)
            else:
                return _Outcome(error=type(exc).__name__)
        if not out.retryable or n == p.maxRetries:
            return out
        time.sleep(_delay(p, n, out.retry_after))
    raise AssertionError("unreachable")  # pragma: no cover


def _as_obj(raw, what: str) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise _RowError(f"{what} n'est pas du JSON valide") from exc
    if not isinstance(raw, dict):
        raise _RowError(f"{what} doit être un objet JSON")
    return raw


def _build_request_parts(p, body_raw, mp_vals) -> tuple[dict, dict]:
    """(en-têtes additionnels, kwargs `requests` du corps). Complété à la Task 4."""
    return {}, {}


def _max_response_bytes() -> int:
    from app.pipelines import connector_runtime as cr

    return cr._env_int("CORE_PIPELINES_HTTP_CALL_MAX_RESPONSE_BYTES", 5 * 1024 * 1024)


def _send_direct(p, url, headers, kwargs, auth, *, follows_redirects: bool) -> _Outcome:
    from app.pipelines.egress import build_guarded_session

    cap = _max_response_bytes()
    with build_guarded_session() as session:
        resp = session.request(
            p.method,
            url,
            headers=headers or None,
            auth=auth,
            timeout=p.timeoutSeconds,
            stream=True,
            allow_redirects=follows_redirects,
            **kwargs,
        )
        try:
            raw = resp.raw.read(cap + 1, decode_content=True)
        finally:
            resp.close()
    if len(raw) > cap:
        return _Outcome(resp.status_code, None, error="réponse trop volumineuse")
    text = raw.decode(resp.encoding or "utf-8", errors="replace")
    return _classify(resp.status_code, text, resp.headers, follows_redirects=follows_redirects)


class _RateLimiter:
    def __init__(self, rps: float | None) -> None:
        self._interval = 1.0 / rps if rps else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if not self._interval:
            return
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self._interval
        if slot > now:
            time.sleep(slot - now)


def _make_row_caller(p, secret_resolver, preview: bool) -> Callable[[tuple], _Outcome]:
    def call(row: tuple) -> _Outcome:
        rn, url, headers_raw, body_raw, *mp_vals = row
        if preview and (p.method != "GET" or rn >= _PREVIEW_MAX_CALLS):
            return _Outcome(error="non exécuté en aperçu", skipped=True)
        if not url:
            return _Outcome(error="URL vide")

        def attempt() -> _Outcome:
            headers = {str(k): str(v) for k, v in _as_obj(headers_raw, "headersExpr").items()}
            extra_headers, kwargs = _build_request_parts(p, body_raw, mp_vals)
            return _send_direct(
                p, url, {**extra_headers, **headers}, kwargs, None, follows_redirects=True
            )

        return _run_with_retry(p, attempt)

    return call


def _stage(conn, p, input_view: str, stage: str) -> None:
    from app.pipelines.expr_validation import validate_bounded_expr

    exprs = {
        "__http_url": p.urlExpr,
        "__http_headers": p.headersExpr or "NULL",
        "__http_body": p.bodyExpr or "NULL",
    }
    for i, f in enumerate(p.multipartFields):
        exprs[f"__mp_{i}"] = f.valueExpr
    for expr in exprs.values():
        validate_bounded_expr(conn, expr)
    cols = ", ".join(f"({e}) AS {_qi(k)}" for k, e in exprs.items())
    conn.execute(
        f"CREATE TEMP TABLE {_qi(stage)} AS "
        f"SELECT (row_number() OVER ()) - 1 AS __rn, *, {cols} FROM {_qi(input_view)}"
    )


def execute_http_call(
    conn,
    *,
    input_view: str,
    view_name: str,
    params: dict,
    secret_resolver=None,
    preview: bool = False,
) -> None:
    from app.pipelines.ops.schemas import TransformHttpCallParams

    p = TransformHttpCallParams.model_validate(params)
    stage = f"{view_name}__stage"
    _stage(conn, p, input_view, stage)
    try:
        _run_staged(conn, p, stage, view_name, secret_resolver, preview)
    finally:
        conn.execute(f"DROP TABLE IF EXISTS {_qi(stage)}")


def _run_staged(conn, p, stage: str, view_name: str, secret_resolver, preview: bool) -> None:
    from app.pipelines import connector_runtime as cr

    out_cols = [p.responseColumn, p.statusCodeColumn, p.statusColumn, p.errorColumn]
    existing = {d[0] for d in conn.execute(f"DESCRIBE {_qi(stage)}").fetchall()}
    clash = sorted(set(out_cols) & existing)
    if clash:
        raise PipelineRuntimeError(
            f"transform.httpCall : colonne(s) de sortie déjà présente(s) en entrée : {clash}"
        )

    mp_cols = [f"__mp_{i}" for i in range(len(p.multipartFields))]
    select = ", ".join(
        _qi(c) for c in ["__rn", "__http_url", "__http_headers", "__http_body", *mp_cols]
    )
    rows = conn.execute(f"SELECT {select} FROM {_qi(stage)} ORDER BY __rn").fetchall()
    if len(rows) > _max_rows():
        raise PipelineRuntimeError(
            f"transform.httpCall : {len(rows)} lignes, plafond de {_max_rows()} dépassé"
        )

    try:
        call = _make_row_caller(p, secret_resolver, preview)
    except cr.ConnectorRuntimeError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    limiter = _RateLimiter(p.requestsPerSecond)

    def one(row: tuple) -> _Outcome:
        limiter.wait()
        return call(row)

    with ThreadPoolExecutor(max_workers=p.maxConcurrency) as pool:
        outcomes = list(pool.map(one, rows))

    df = pd.DataFrame(
        {
            "__rn": [r[0] for r in rows],
            "r": [o.body for o in outcomes],
            "c": pd.array([o.code for o in outcomes], dtype="Int64"),
            "s": [o.status for o in outcomes],
            "e": [o.error for o in outcomes],
        }
    )
    conn.register("_http_call_results", df)
    try:
        excl = ", ".join(_qi(c) for c in [*_INTERNAL, *mp_cols])
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS "
            f"SELECT t.* EXCLUDE ({excl}), "
            f"CAST(r.r AS VARCHAR) AS {_qi(p.responseColumn)}, "
            f"CAST(r.c AS INTEGER) AS {_qi(p.statusCodeColumn)}, "
            f"CAST(r.s AS VARCHAR) AS {_qi(p.statusColumn)}, "
            f"CAST(r.e AS VARCHAR) AS {_qi(p.errorColumn)} "
            f"FROM {_qi(stage)} t JOIN _http_call_results r ON r.__rn = t.__rn ORDER BY t.__rn"
        )
    finally:
        conn.unregister("_http_call_results")
