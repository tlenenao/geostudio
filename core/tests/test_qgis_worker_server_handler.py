# SPDX-License-Identifier: Apache-2.0
"""Tests légers du sidecar deploy/qgis-worker/server.py (Handler.do_POST),
sans qgis_process ni conteneur — même esprit que les tests transform.qgis
"sans sidecar réel" de test_pipeline_runtime.py (final review Finding 3).
server.py n'est pas un module du package core (pas de test infra existante
dans deploy/qgis-worker/) : chargé ici par chemin de fichier, après avoir
neutralisé la lecture de /app/allowlist.txt (chemin en dur, valide
seulement à l'intérieur du conteneur qgis-worker) — jamais exercée par les
tests ci-dessous, tous rejetés par le guard de parsing avant le contrôle
d'appartenance à l'allowlist."""
import importlib.util
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

_SERVER_PATH = Path(__file__).resolve().parents[2] / "deploy" / "qgis-worker" / "server.py"


def _load_server_module():
    spec = importlib.util.spec_from_file_location("qgis_worker_server", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    # dont_write_bytecode : évite de laisser un deploy/qgis-worker/__pycache__
    # non trackable (deploy/ n'a pas de .gitignore __pycache__, contrairement
    # à core/) comme sous-produit de ce chargement dynamique hors package.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        with patch("pathlib.Path.read_text", return_value="native:centroids\n"):
            spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


@pytest.fixture()
def running_worker():
    module = _load_server_module()
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_do_post_non_json_body_returns_clean_400(running_worker):
    """A non-JSON body used to raise an unhandled json.JSONDecodeError inside
    do_POST — must now respond 400 with a clean JSON error body via the
    existing _respond helper, not crash the request handler."""
    response = httpx.post(f"{running_worker}/run", content=b"not json at all", timeout=5)
    assert response.status_code == 400
    assert "error" in response.json()


def test_do_post_missing_algorithm_id_returns_clean_400(running_worker):
    """A well-formed JSON body missing "algorithmId" used to raise an
    unhandled KeyError."""
    response = httpx.post(f"{running_worker}/run", json={"inputs": {}}, timeout=5)
    assert response.status_code == 400
    assert "error" in response.json()


def test_do_post_missing_inputs_returns_clean_400(running_worker):
    """A well-formed JSON body missing "inputs" used to raise an unhandled
    KeyError."""
    response = httpx.post(
        f"{running_worker}/run", json={"algorithmId": "native:centroids"}, timeout=5,
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_do_post_valid_request_still_reaches_allowlist_check(running_worker):
    """Sanity check that the new guard doesn't swallow well-formed requests :
    a well-formed body for an algorithm NOT on the (stubbed) allowlist must
    still reach the pre-existing 403 path, unaffected by the parsing guard."""
    response = httpx.post(
        f"{running_worker}/run",
        json={"algorithmId": "native:totallymadeup", "inputs": {}},
        timeout=5,
    )
    assert response.status_code == 403
    assert "non autorisé" in response.json()["error"]
