# SPDX-License-Identifier: Apache-2.0
"""Wrapper HTTP minimal autour de qgis_process (design SP-15d §3). Une
seule route, POST /run : shelle `qgis_process run <algorithmId> -` avec les
inputs en JSON sur stdin, retranscrit le contrat exit-code/stdout/stderr
vérifié empiriquement en design en réponse HTTP. Aucune logique métier
au-delà du contrôle d'appartenance à allowlist.txt (une garde de sécurité,
pas une transformation de données — design §3)."""
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ALLOWLIST_PATH = Path("/app/allowlist.txt")
# Marge au-dessus du timeout HTTP worker->qgis-worker (design §8, 600s par
# défaut) : le sous-process est tué en premier, jamais la connexion HTTP.
QGIS_TIMEOUT_SECONDS = 900


def _load_allowlist() -> set[str]:
    return {line.strip() for line in ALLOWLIST_PATH.read_text().splitlines() if line.strip()}


_ALLOWLIST = _load_allowlist()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/run":
            self._respond(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        algorithm_id = body["algorithmId"]
        inputs = body["inputs"]

        if algorithm_id not in _ALLOWLIST:
            self._respond(403, {"error": f"algorithme non autorisé : {algorithm_id}"})
            return

        try:
            result = subprocess.run(
                ["qgis_process", "run", algorithm_id, "-"],
                input=json.dumps({"inputs": inputs}),
                capture_output=True, text=True, timeout=QGIS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            self._respond(504, {"error": f"timeout après {QGIS_TIMEOUT_SECONDS}s"})
            return

        if result.returncode != 0:
            error_line = next(
                (line for line in result.stderr.splitlines() if line.startswith("ERROR:")),
                "qgis_process a échoué sans message ERROR: identifiable",
            )
            self._respond(502, {"error": error_line})
            return

        self._respond(200, json.loads(result.stdout))

    def _respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass  # évite de polluer stdout du conteneur ; pas d'instrumentation OTel v0 (design §8)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()
