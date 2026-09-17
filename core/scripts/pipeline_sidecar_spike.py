# SPDX-License-Identifier: Apache-2.0
"""Spike PyInstaller (design docs/superpowers/specs/2026-09-17-desktop-etl-
standalone-design.md §9) : fige app.pipelines.connector_runtime — et tout
son graphe d'imports transitif (dlt, duckdb, sqlalchemy, geopandas, pyarrow,
shapely, pyproj) — en binaire autonome, puis exécute un reader.connector.rest
réel contre un serveur HTTP local (aucun réseau externe requis) pour confirmer
que le freeze n'a rien perdu.

Sert de point d'entrée PyInstaller (Task 3 du plan) ET de script exécutable
directement pour la vérification "non gelé" de contrôle (Task 2)."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import duckdb

from app.pipelines import egress as pipelines_egress
from app.pipelines.connector_runtime import materialize_rest_connector
from app.pipelines.ops.schemas import ReaderConnectorRestParams

_RECORDS = [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}, {"id": 3, "name": "gamma"}]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(_RECORDS).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:  # silence stderr par défaut
        pass


def main() -> int:
    # Même rationale que la fixture `_no_ssrf_guard` de
    # tests/test_pipeline_connector_runtime.py : la garde bloque
    # légitimement 127.0.0.1 (loopback) — neutralisation ponctuelle en
    # mémoire, dans ce process jetable, pour taper un serveur local offline.
    pipelines_egress.assert_egress_allowed = lambda url: None

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = duckdb.connect(":memory:")
        params = ReaderConnectorRestParams(baseUrl=f"http://127.0.0.1:{port}/", path="items")
        materialize_rest_connector(
            conn,
            # secretName reste None (défaut) => _resolve_secret court-circuite
            # avant tout accès DB : session=None est donc valide ICI
            # uniquement (cf. Global Constraints du plan).
            session=None,  # type: ignore[arg-type]
            tenant_id="spike",
            node_id="n1",
            params=params,
            view_name="v1",
        )
        count = conn.execute("SELECT count(*) FROM v1").fetchone()[0]
    finally:
        server.shutdown()

    expected = len(_RECORDS)
    if count != expected:
        print(f"FAIL: expected {expected} rows, got {count}", file=sys.stderr)
        return 1
    print(f"OK: {count} rows materialized via reader.connector.rest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
