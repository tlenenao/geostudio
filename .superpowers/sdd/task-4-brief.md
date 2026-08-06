## Task 4: `qgis-worker` sidecar service

**Files:**
- Create: `deploy/qgis-worker/Dockerfile`
- Create: `deploy/qgis-worker/server.py`
- Create: `deploy/qgis-worker/allowlist.txt` (generated)
- Create: `scripts/generate_qgis_worker_allowlist.py`
- Modify: `core/tests/conftest.py`
- Modify: `core/pyproject.toml` (new pytest marker)
- Test: `core/tests/test_qgis_worker_sidecar.py`

**Interfaces:**
- Produces: a `POST /run` HTTP contract (`{"algorithmId": str, "inputs":
  dict}` → `200 {...qgis_process JSON...}` | `403 {"error": str}` (not
  allowlisted) | `502 {"error": str}` (qgis_process failed) | `504
  {"error": str}` (timeout)). Consumed by Task 5 (`runtime.py`'s HTTP call).
- Produces: `qgis_worker_url` and `qgis_scratch_dir` session-scoped pytest
  fixtures in `core/tests/conftest.py`, skipping (marker `qgis`) if the
  required env vars are unset — consumed by this task's test and Task 8's.

- [ ] **Step 1: Write the allowlist-ids generator (ids only, no schemas)**

Create `scripts/generate_qgis_worker_allowlist.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Régénère deploy/qgis-worker/allowlist.txt (un id par ligne) depuis la
même liste ALLOWLIST_IDS que scripts/generate_qgis_algorithm_schemas.py —
dupliquée ici plutôt qu'importée (le sidecar ne dépend jamais de core/,
design SP-15d §3/§4 : isolation totale). Relancer si l'allowlist change,
en même temps que generate_qgis_algorithm_schemas.py."""
from pathlib import Path

from generate_qgis_algorithm_schemas import ALLOWLIST_IDS

OUTPUT_PATH = Path(__file__).parent.parent / "deploy" / "qgis-worker" / "allowlist.txt"


def main() -> None:
    OUTPUT_PATH.write_text("\n".join(sorted(ALLOWLIST_IDS)) + "\n")
    print(f"wrote {len(ALLOWLIST_IDS)} ids to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd scripts && python generate_qgis_worker_allowlist.py`
Expected: `wrote 50 ids to .../deploy/qgis-worker/allowlist.txt`, a 50-line
text file, one algorithm id per line, sorted.

- [ ] **Step 3: Write the sidecar HTTP wrapper**

Create `deploy/qgis-worker/server.py`:

```python
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
```

- [ ] **Step 4: Write the Dockerfile**

Create `deploy/qgis-worker/Dockerfile`:

```dockerfile
# qgis/qgis:release-3_34 = QGIS 3.34.5 "Prizren" (LTR) — PAS :latest, qui
# pointe vers un build 4.3.0-Master instable (vérifié en design, §2).
FROM qgis/qgis:release-3_34

# grassprovider fournit les ids grass7:* (dont grass7:r.watershed, le cas
# hydrologie de l'étude de faisabilité) mais est désactivé par défaut —
# vérifié en design (qgis_process plugins list). L'activer ici l'écrit dans
# le profil QGIS gravé dans cette image ; l'activer au runtime ne
# survivrait pas à un `docker run --rm` frais (design §2 point 6).
RUN qgis_process plugins enable grassprovider

COPY server.py /app/server.py
COPY allowlist.txt /app/allowlist.txt

ENV QT_QPA_PLATFORM=offscreen

CMD ["python3", "/app/server.py"]
```

- [ ] **Step 5: Build the image and smoke-test it manually**

Run:
```bash
docker build -t geostudio-qgis-worker deploy/qgis-worker
sudo mkdir -p /scratch && sudo chown "$(whoami)" /scratch
docker run -d --rm --name qgis-worker-test -p 8300:8000 -v /scratch:/scratch geostudio-qgis-worker
```
Expected: container starts and stays up (`docker ps` shows
`qgis-worker-test`). If `/scratch` already exists and is owned by someone
else, `chown` will fail loudly — that's the one-time local setup this
plan's `qgis`-marked tests require (mirrors the existing `postgis` marker's
own pre-provisioned-container convention, see `core/tests/conftest.py`'s
`pg_engine` fixture).

- [ ] **Step 6: Add the `qgis` marker and fixtures**

Modify `core/pyproject.toml` — extend the `markers` list:

```python
markers = [
    "postgis: nécessite un PostGIS réel (CORE_TEST_DATABASE_URL) ; skippé sinon",
    "qgis: nécessite un sidecar qgis-worker réel (CORE_TEST_QGIS_WORKER_URL) ; skippé sinon",
]
```

Modify `core/tests/conftest.py` — add after the existing `pg_engine`
fixture:

```python
@pytest.fixture(scope="session")
def qgis_worker_url():
    url = os.environ.get("CORE_TEST_QGIS_WORKER_URL")
    if not url:
        pytest.skip("CORE_TEST_QGIS_WORKER_URL non défini — test qgis skippé")
    return url


@pytest.fixture(scope="session")
def qgis_scratch_dir():
    path = os.environ.get("CORE_TEST_QGIS_SCRATCH_DIR")
    if not path:
        pytest.skip("CORE_TEST_QGIS_SCRATCH_DIR non défini — test qgis skippé")
    return Path(path)
```

Add `from pathlib import Path` to `conftest.py`'s imports if not already
present (it is — reused from the `pg_engine`/other fixtures' existing
imports; verify, add only if missing).

- [ ] **Step 7: Write the failing tests**

Create `core/tests/test_qgis_worker_sidecar.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Exercise le vrai sidecar qgis-worker (conteneur pré-démarré par le
développeur, cf. Task 4 Step 5 de docs/superpowers/plans/
2026-08-06-sp15d-qgis-sidecar.md). export CORE_TEST_QGIS_WORKER_URL=
http://localhost:8300 CORE_TEST_QGIS_SCRATCH_DIR=/scratch avant de lancer."""
import geopandas as gpd
import httpx
import pytest
from shapely.geometry import Polygon

pytestmark = pytest.mark.qgis


def _write_test_polygon(scratch_dir, name: str) -> None:
    gdf = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])], crs="EPSG:4326",
    )
    gdf.to_file(scratch_dir / name, driver="GPKG")


def test_run_allowlisted_algorithm_succeeds(qgis_worker_url, qgis_scratch_dir):
    _write_test_polygon(qgis_scratch_dir, "in_centroids.gpkg")
    response = httpx.post(
        f"{qgis_worker_url}/run",
        json={
            "algorithmId": "native:centroids",
            "inputs": {
                "INPUT": "/scratch/in_centroids.gpkg", "ALL_PARTS": False,
                "OUTPUT": "/scratch/out_centroids.gpkg",
            },
        },
        timeout=30,
    )
    assert response.status_code == 200
    assert response.json()["results"]["OUTPUT"] == "/scratch/out_centroids.gpkg"
    assert (qgis_scratch_dir / "out_centroids.gpkg").exists()


def test_run_rejects_non_allowlisted_algorithm(qgis_worker_url):
    response = httpx.post(
        f"{qgis_worker_url}/run",
        json={"algorithmId": "native:totallymadeup", "inputs": {}},
        timeout=30,
    )
    assert response.status_code == 403
    assert "non autorisé" in response.json()["error"]


def test_run_propagates_qgis_error_for_missing_input(qgis_worker_url):
    response = httpx.post(
        f"{qgis_worker_url}/run",
        json={
            "algorithmId": "native:centroids",
            "inputs": {
                "INPUT": "/scratch/does-not-exist.gpkg", "ALL_PARTS": False,
                "OUTPUT": "/scratch/out_missing.gpkg",
            },
        },
        timeout=30,
    )
    assert response.status_code == 502
    assert response.json()["error"].startswith("ERROR:")
```

- [ ] **Step 8: Run tests to verify they fail without the sidecar**

Run: `cd core && uv run pytest tests/test_qgis_worker_sidecar.py -v`
Expected (no env vars set): 3 skipped, `CORE_TEST_QGIS_WORKER_URL non
défini`.

- [ ] **Step 9: Run tests against the real sidecar**

Run:
```bash
export CORE_TEST_QGIS_WORKER_URL=http://localhost:8300
export CORE_TEST_QGIS_SCRATCH_DIR=/scratch
cd core && uv run pytest tests/test_qgis_worker_sidecar.py -v
```
Expected: 3 passed, against the container started in Step 5.

- [ ] **Step 10: Commit**

```bash
git add deploy/qgis-worker/ scripts/generate_qgis_worker_allowlist.py \
  core/tests/conftest.py core/pyproject.toml core/tests/test_qgis_worker_sidecar.py
git commit -m "feat(deploy): qgis-worker sidecar — isolated qgis_process HTTP wrapper"
```

---

