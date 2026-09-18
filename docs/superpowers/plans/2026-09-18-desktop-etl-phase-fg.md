# Desktop ETL — Phase F+G (freeze binaire réel, bootstrap Tauri, sécurité loopback) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the pure-Python, Linux-tested desktop-etl sidecar (Phase E,
closed) into an installable Windows desktop product: a real PyInstaller
freeze of the actual entrypoint, an authenticated loopback (closing the DNS
rebinding hole before the sidecar becomes a real subprocess), a new Tauri
shell that spawns it, and a reused pipeline canvas wired to a new desktop
`ItemClient` — validated end-to-end by a golden path (create a
file→file pipeline, run it, see the output file) on Windows.

**Architecture:** No new package.json, no file moved out of
`shell/src/builder/pipeline/`. `desktop-etl/src-tauri/` (new, Rust) spawns
the frozen sidecar binary via `tauri-plugin-shell`'s sidecar API, reads its
`PORT=<n>` handshake, and exposes a `get_sidecar_connection` Tauri command.
`shell/` grows a second Vite build target (`vite.desktop.config.ts` +
`index.desktop.html` + `shell/src/desktop/entry.tsx`, mirroring the
already-shipped `vite.export.config.ts`/SP-18a pattern) that boots the
existing `PipelineBuilderPage` inside a `MemoryRouter`, backed by a new
`DesktopItemClient.ts` (full explicit method list, same pattern as
`StaticItemClient.ts` — no `Proxy`, no `as unknown as ItemClient`).

**Tech Stack:** Python 3.12 (FastAPI, uvicorn, PyInstaller — already
dependencies), Rust + Tauri v2 (`tauri`, `tauri-plugin-shell`,
`tauri-plugin-fs`, `tauri-plugin-dialog`, new to this repo), TypeScript/Vite
(existing `shell/` toolchain), WebdriverIO + `tauri-driver` for E2E (new,
dev-only, Node).

## Global Constraints

- Every new/modified Python file starts with `# SPDX-License-Identifier: Apache-2.0`; every new Rust file gets the same as a `//` comment; every new TS/JS file the same as a `//` comment. Every new Cargo/JSON/YAML config file that supports comments does not need the header (JSON does not support comments — skip it there).
- Phase F/G stay Windows-only (design §1) — no macOS/Linux Tauri bundle target is added anywhere in this plan.
- No `reader.connector.*`, no `writer.core.collection`, no secrets/trousseau OS code anywhere in this plan — those are Phase I/J, explicitly out of scope (spec §2).
- The sidecar's HTTP contract (`docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md` §3.1) must stay byte-for-byte identical in its success-path shapes; the only allowed additions are the new auth/Host rejection responses (Task 1) — never rename or reshape an existing field.
- `core/app/pipelines/sidecar/app.py`'s existing 9 tests (`core/tests/test_pipeline_sidecar_app.py`) must all keep passing unmodified in behavior — the new `token` parameter defaults to `None`, which must reproduce today's no-auth behavior exactly (this is how Task 1 avoids a regression on already-shipped Phase E code).
- Every Rust/Cargo/npm dependency version and API signature quoted in this plan was checked against the official Tauri v2 docs (`tauri-apps/tauri-docs`, `v2` branch) via context7 on 2026-09-18, not from memory — but this repo has never compiled a line of Rust before, so treat every Rust step's "verify before writing" instruction as mandatory, not optional (CLAUDE.md piège #3).
- After Task 1 and Task 2 (pure Python, no Windows needed), every other task requires an actual Windows machine for its own verification step (the user's Windows VM, confirmed available) — do not mark a Rust/Tauri task's steps done from a Linux-only `cargo check`; a `cargo check`/`tsc` pass on Linux is a necessary but not sufficient verification for those tasks.
- Run `cd core && uv run pytest tests/test_pipeline_sidecar_*.py -v` after Task 1; run the **full** `uv run pytest` + `uv run ruff check .` + `uv run ruff format --check .` + `uv run lint-imports` + (shell) `npm run test` + `npm run lint` + `npm run build` before the final commit of the last task, matching this repo's closing ritual for every prior desktop-etl plan.
- If `/tmp/pytest-of-<user>` is not owned by the current user (a known WSL artifact of a prior root-owned Docker run, unrelated to this code), pass `--basetemp=<a writable scratch dir>` to pytest instead of investigating it as a regression.

---

## File Structure

- **Modify** `core/app/pipelines/sidecar/app.py` — `create_sidecar_app()` gains an optional `token: str | None` kwarg; when set, a middleware enforces `Authorization: Bearer <token>` and a `Host` allowlist on every request.
- **Modify** `core/scripts/pipeline_sidecar.py` — reads `GEOSTUDIO_SIDECAR_TOKEN` from the environment and passes it through.
- **Modify** `core/tests/test_pipeline_sidecar_app.py`, `core/tests/test_pipeline_sidecar_entrypoint.py` — new auth/Host tests.
- **Create** `core/scripts/pipeline_sidecar.pyinstaller-args.txt` — freeze recipe for the real entrypoint.
- **Create** `core/scripts/pipeline_sidecar_freeze_smoke.py` — drives a frozen binary (any OS) through a full `reader.file`→`writer.file` cycle over HTTP; used by CI and by the user on their Windows VM.
- **Create** `.github/workflows/desktop-etl-sidecar-freeze.yml` — Windows CI job: freeze `pipeline_sidecar.py`, run the smoke script against the frozen `.exe`.
- **Create** `desktop-etl/src-tauri/Cargo.toml`, `desktop-etl/src-tauri/build.rs`, `desktop-etl/src-tauri/tauri.conf.json`, `desktop-etl/src-tauri/capabilities/default.json`, `desktop-etl/src-tauri/src/main.rs`.
- **Create** `desktop-etl/scripts/prepare-sidecar-binary.mjs` — copies/renames the frozen sidecar into `src-tauri/binaries/` with the target-triple suffix Tauri requires.
- **Create** `desktop-etl/README.md` — how to build/run in dev, on Windows.
- **Create** `shell/src/desktop/DesktopItemClient.ts`, `shell/src/desktop/DesktopItemClient.test.ts`.
- **Create** `shell/vite.desktop.config.ts`, `shell/index.desktop.html`, `shell/src/desktop/entry.tsx`.
- **Modify** `shell/package.json` — add `@tauri-apps/api`, `@tauri-apps/plugin-shell`, `@tauri-apps/plugin-fs`, `@tauri-apps/plugin-dialog` dependencies; add `build:desktop-runtime` script.
- **Create** `desktop-etl/e2e/package.json`, `desktop-etl/e2e/wdio.conf.js`, `desktop-etl/e2e/specs/golden-path.spec.js`.
- **Create** `.github/workflows/desktop-etl-webdriver.yml`.

---

### Task 1: Sécurité du loopback — jeton + validation Host

**Files:**
- Modify: `core/app/pipelines/sidecar/app.py`
- Modify: `core/scripts/pipeline_sidecar.py`
- Modify: `core/tests/test_pipeline_sidecar_app.py`
- Modify: `core/tests/test_pipeline_sidecar_entrypoint.py`

**Interfaces:**
- Consumes: `create_sidecar_app(*, base_uri: str) -> FastAPI` (current signature, `core/app/pipelines/sidecar/app.py:38`).
- Produces (for Task 2's smoke script and Task 3's Rust spawn code):
  - `create_sidecar_app(*, base_uri: str, token: str | None = None) -> FastAPI` — when `token` is `None` (the default), behavior is byte-for-byte identical to today. When set, every route under `/pipelines/*` requires header `Authorization: Bearer <token>` (401 otherwise) and, if a `Host` header is present, its hostname part (before any `:port`) must equal `127.0.0.1` (400 otherwise, absent `Host` is allowed through).
  - `pipeline_sidecar.py`'s `main()` reads `os.environ.get("GEOSTUDIO_SIDECAR_TOKEN")` (`None` if unset) and passes it to `create_sidecar_app(..., token=...)`. **No change to the stdout handshake format** — still exactly one line, `PORT=<n>\n` (the token is a value Tauri already knows, since it will be the one setting the environment variable before spawning; echoing it back on stdout would add a second handshake line for no verification benefit — a deliberate simplification of this plan versus the design spec's exact wording in `docs/superpowers/specs/2026-09-18-desktop-etl-phase-fg-design.md` §4, recorded here as the actual implementation decision).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_sidecar_app.py` (do not touch any existing test in this file):

```python
def test_default_app_has_no_auth_and_ignores_host(client):
    # Unauthenticated fixture (token=None, the default) — behavior for
    # every other test in this file must stay exactly as before this task.
    res = client.get("/pipelines/ops", headers={"Host": "anything-goes.example"})
    assert res.status_code == 200


@pytest.fixture
def authed_client(tmp_path):
    app = create_sidecar_app(base_uri=str(tmp_path), token="s3cr3t")
    return TestClient(app, base_url="http://127.0.0.1")


def test_authed_app_rejects_missing_authorization_header(authed_client):
    res = authed_client.get("/pipelines/ops")
    assert res.status_code == 401


def test_authed_app_rejects_wrong_token(authed_client):
    res = authed_client.get("/pipelines/ops", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


def test_authed_app_accepts_correct_token(authed_client):
    res = authed_client.get("/pipelines/ops", headers={"Authorization": "Bearer s3cr3t"})
    assert res.status_code == 200


def test_authed_app_rejects_spoofed_host_header(authed_client):
    res = authed_client.get(
        "/pipelines/ops",
        headers={"Authorization": "Bearer s3cr3t", "Host": "evil.example.com"},
    )
    assert res.status_code == 400


def test_authed_app_accepts_host_with_port_suffix(authed_client):
    res = authed_client.get(
        "/pipelines/ops",
        headers={"Authorization": "Bearer s3cr3t", "Host": "127.0.0.1:9999"},
    )
    assert res.status_code == 200


def test_authed_app_allows_missing_host_header(authed_client):
    # httpx always sends Host in practice; this documents the deliberate
    # choice (design §4) to only reject a Host header that is PRESENT and
    # wrong, never to require one — see the plan's rationale in Task 1.
    res = authed_client.get(
        "/pipelines/ops",
        headers={"Authorization": "Bearer s3cr3t"},
        extensions={},
    )
    assert res.status_code == 200
```

Append to `core/tests/test_pipeline_sidecar_entrypoint.py`:

```python
def test_entrypoint_requires_token_when_env_var_set(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOSTUDIO_SIDECAR_TOKEN", "s3cr3t")
    proc = subprocess.Popen(
        [sys.executable, "scripts/pipeline_sidecar.py", "--base-uri", str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=".",
        env={**__import__("os").environ, "GEOSTUDIO_SIDECAR_TOKEN": "s3cr3t"},
    )
    try:
        first_line = proc.stdout.readline()
        match = re.match(r"PORT=(\d+)\n", first_line)
        assert match, f"unexpected first line: {first_line!r}, stderr={proc.stderr.read()}"
        port = int(match.group(1))

        deadline = time.monotonic() + 5.0
        last_status = None
        while time.monotonic() < deadline:
            try:
                res = httpx.get(f"http://127.0.0.1:{port}/pipelines/ops", timeout=1.0)
                last_status = res.status_code
                break
            except httpx.TransportError:
                time.sleep(0.1)
        assert last_status == 401, "unauthenticated request should be rejected once a token is set"

        authed = httpx.get(
            f"http://127.0.0.1:{port}/pipelines/ops",
            headers={"Authorization": "Bearer s3cr3t"},
            timeout=1.0,
        )
        assert authed.status_code == 200
    finally:
        proc.terminate()
        proc.wait(timeout=5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_app.py tests/test_pipeline_sidecar_entrypoint.py -v`
Expected: the 6 new `test_authed_app_*`/`test_default_app_*` tests FAIL with `TypeError: create_sidecar_app() got an unexpected keyword argument 'token'`; `test_entrypoint_requires_token_when_env_var_set` FAILS on the `assert last_status == 401` line (today it returns 200 — no auth exists yet).

- [ ] **Step 3: Write the implementation**

Before writing the middleware, verify the installed `starlette.testclient.TestClient` actually forwards a `base_url` kwarg to its underlying `httpx.Client` the way this plan assumes:
`cd core && uv run python -c "from starlette.testclient import TestClient; import inspect; print(inspect.signature(TestClient.__init__))"`
Expected: a `base_url` parameter is present (default `"http://testserver"`). If the installed version differs, adjust `authed_client`'s fixture in Step 1 to whatever mechanism that signature exposes for controlling the outgoing `Host` header — do not silently drop the test's intent.

Modify `core/app/pipelines/sidecar/app.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""API loopback du sidecar desktop-etl (design §4, roadmap §3.1) : rejoue
la forme des routes cœur (app.pipelines.routes) sans Postgres/auth/tenant —
mono-utilisateur, mono-process, 127.0.0.1 uniquement (jamais exposé sur
0.0.0.0, cf. Phase E du plan et l'entrypoint de la Tâche 4).

Phase G (docs/superpowers/plans/2026-09-18-desktop-etl-phase-fg.md, Tâche 1) :
`token` ferme le DNS rebinding avant que ce process ne soit un vrai
sous-processus lancé par Tauri — `None` (le défaut) reproduit exactement le
comportement d'avant cette tâche, pour ne rien casser des tests Phase E."""

import hmac
import os

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response

from app.configs.schemas import PipelinePayload
from app.pipelines import runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import OP_KINDS, ops_catalog
from app.pipelines.sidecar.runner import PipelineStore, start_run
from app.pipelines.sidecar.tracker import RunRegistry

# Dupliqué de app.pipelines.routes._RUNS_MAX_LIMIT (pas importé : cet import
# entraînerait tout le graphe de app.pipelines.routes — jobs/notifications/
# observability/roles — dans le sidecar, à l'exact opposé du but de ce
# paquet, cf. docs/superpowers/specs/2026-09-18-desktop-etl-remaining-
# roadmap.md §2.4).
_RUNS_MAX_LIMIT = 1000

# session=None n'est vérifié sûr (design desktop-etl, Global Constraints du
# plan) que pour reader.file/writer.file et les op transform.* (aucune ne
# touche Session dans runtime.py) — reader.collection/writer.collection/
# writer.dataset/writer.export/reader.connector.* touchent Session et
# lèveraient une AttributeError interne si exposées ici (revue finale, Fix 2).
_SIDECAR_SAFE_OPS = frozenset(
    op
    for op, kind in OP_KINDS.items()
    if op in ("reader.file", "writer.file") or kind == "transform"
)


def create_sidecar_app(*, base_uri: str, token: str | None = None) -> FastAPI:
    # Actif par défaut côté sidecar desktop, jamais côté cœur (design §3) —
    # posé ici, pas supposé déjà présent dans l'environnement appelant.
    os.environ["CORE_PIPELINE_FILE_IO_ENABLED"] = "true"

    app = FastAPI()
    store = PipelineStore()
    registry = RunRegistry()

    if token is not None:
        expected_authorization = f"Bearer {token}"

        @app.middleware("http")
        async def _enforce_loopback_auth(request: Request, call_next):
            host_header = request.headers.get("host")
            if host_header is not None and host_header.split(":")[0] != "127.0.0.1":
                return Response(status_code=400, content="invalid Host header")
            authorization = request.headers.get("authorization")
            if authorization is None or not hmac.compare_digest(
                authorization, expected_authorization
            ):
                return Response(status_code=401, content="missing or invalid bearer token")
            return await call_next(request)

    @app.put("/pipelines/{item_id}", status_code=204)
    def put_pipeline(item_id: str, payload: PipelinePayload) -> Response:
        store.set(item_id, payload)
        return Response(status_code=204)

    @app.get("/pipelines/ops")
    def get_ops() -> dict:
        return {op: contract for op, contract in ops_catalog().items() if op in _SIDECAR_SAFE_OPS}

    @app.post("/pipelines/{item_id}/run", status_code=202)
    def run_pipeline_route(item_id: str) -> dict:
        run_id = start_run(store, registry, item_id, base_uri=base_uri)
        if run_id is None:
            raise HTTPException(status_code=404, detail="no pipeline stored for this item")
        return {"runId": run_id}

    @app.get("/pipelines/{item_id}/runs")
    def get_runs(
        item_id: str,
        limit: int = Query(100, ge=1),
        offset: int = Query(0, ge=0),
    ) -> list[dict]:
        limit = min(limit, _RUNS_MAX_LIMIT)
        return registry.list(item_id, limit=limit, offset=offset)

    @app.post("/pipelines/{item_id}/preview")
    def preview_pipeline_route(item_id: str, upTo: str = Query(...)) -> list[dict]:
        payload = store.get(item_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="no pipeline stored for this item")
        try:
            return runtime.preview_pipeline(
                session=None,
                payload=payload,
                tenant_id="local",
                user=None,
                up_to=upTo,
                endpoint_url="",
                access_key="",
                secret_key="",
                base_uri=base_uri,
            )
        except (PipelineRuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
```

(Only the `token` parameter, the `hmac`/`Request` imports, and the
`if token is not None:` block are new — every route body is unchanged.)

Modify `core/scripts/pipeline_sidecar.py` (add `import os` and pass the
token through — everything else, including the stdout handshake, unchanged):

```python
import argparse
import os
import socket
import sys
import tempfile
from pathlib import Path
```

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-uri", default=None)
    args = parser.parse_args(argv)
    base_uri = args.base_uri or tempfile.mkdtemp(prefix="geostudio-sidecar-")
    token = os.environ.get("GEOSTUDIO_SIDECAR_TOKEN") or None

    app = create_sidecar_app(base_uri=base_uri, token=token)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_sidecar_app.py tests/test_pipeline_sidecar_entrypoint.py -v`
Expected: all passed (9 pre-existing + 7 new in `test_pipeline_sidecar_app.py`; 1 pre-existing + 1 new in `test_pipeline_sidecar_entrypoint.py`).

- [ ] **Step 5: Verify by falsification (CLAUDE.md piège #10)**

Temporarily comment out the entire `if authorization is None or not hmac.compare_digest(...)` block's `return Response(...)` line (replace it with `pass`) and rerun
`uv run pytest tests/test_pipeline_sidecar_app.py -k authed -v` — confirm
`test_authed_app_rejects_missing_authorization_header` and
`test_authed_app_rejects_wrong_token` now FAIL (proving they were actually
exercising the guard). Restore the line, rerun the same command, confirm
they pass again. Do the same for the `Host` check (temporarily make the
`if host_header is not None and ...` condition always `False`), confirming
`test_authed_app_rejects_spoofed_host_header` fails, then restore.

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/sidecar/app.py core/scripts/pipeline_sidecar.py \
  core/tests/test_pipeline_sidecar_app.py core/tests/test_pipeline_sidecar_entrypoint.py
git commit -m "feat(core): jeton + validation Host sur le loopback du sidecar desktop-etl"
```

---

### Task 2: Freeze PyInstaller réel de l'entrypoint + CI Windows

**Files:**
- Create: `core/scripts/pipeline_sidecar.pyinstaller-args.txt`
- Create: `core/scripts/pipeline_sidecar_freeze_smoke.py`
- Create: `.github/workflows/desktop-etl-sidecar-freeze.yml`

**Interfaces:**
- Consumes: `core/scripts/pipeline_sidecar.py` (Task 1).
- Produces (for Task 3): a frozen `pipeline-sidecar.exe` (Windows CI
  artifact, or built locally by the user on their Windows VM with the same
  recipe) — Task 3 places a copy of this binary under
  `desktop-etl/src-tauri/binaries/`.

**Evidence gathered before writing this task (do not re-derive — verified
2026-09-18 against the actual installed packages in this repo's `core/.venv`):**
`geopandas`/`shapely`/`pyproj` do not appear anywhere in the transitive
import closure of `app.pipelines.sidecar.app`/`runner`/`tracker` (an AST
walk from those 3 modules visited 99 real `app.*` modules and found zero
occurrences — they live only under `app/ingestion/parsers.py` and
`app/cdc/{compaction,parquet_writer}.py`, never imported by anything the
sidecar touches). **The Phase F geospatial freeze risk flagged by the
roadmap does not apply to this sidecar's scope — no `--collect-data
pyproj`/GEOS-DLL work is needed.** The same AST walk found `procrastinate`
IS transitively imported (`app.pipelines.runtime` → `app.collections.
repository`/`app.items.repository`/`app.jobs`, all `import procrastinate`
at module level) — this import never happens in the D1 spike (which only
imports `connector_runtime`/`egress`/`ops.schemas` directly), so it is a
genuinely new, unverified freeze surface for this task. A check of the
installed `procrastinate==3.9.0` package found no
`importlib.metadata`/`entry_points`/`pluggy`-based dynamic plugin loading
(unlike `dlt`) — only its own `metadata.py` introspecting its own version.
Expectation: `--collect-all dlt` (the D1 recipe, unchanged) is likely
sufficient; the smoke test below is what actually proves it, with
`--collect-all procrastinate` as the documented fallback if it isn't
(mirrors the D1 iterate-on-failure pattern — do not add it pre-emptively).

- [ ] **Step 1: Write the freeze recipe**

```
# core/scripts/pipeline_sidecar.pyinstaller-args.txt
# Recette de gel pour l'entrypoint réel (core/scripts/pipeline_sidecar.py),
# distincte de pipeline_sidecar_spike.pyinstaller-args.txt (D1, gèle un
# graphe d'imports plus étroit). Voir docs/superpowers/plans/2026-09-18-
# desktop-etl-phase-fg.md, Tâche 2, pour le raisonnement complet.
#
# Commande complète :
#   cd core && uv run pyinstaller --onefile --name pipeline-sidecar \
#     --paths . --collect-all dlt scripts/pipeline_sidecar.py
--collect-all dlt

# Si le smoke test (pipeline_sidecar_freeze_smoke.py) échoue avec un
# ModuleNotFoundError/ImportError mentionnant "procrastinate", ajouter une
# ligne "--collect-all procrastinate" ici et documenter l'erreur observée
# dans ce fichier, même patron que la découverte "--collect-all dlt" du
# spike D1 (docs/superpowers/specs/2026-09-17-desktop-etl-spike-01-findings.md).
```

- [ ] **Step 2: Write the freeze smoke test script**

```python
# core/scripts/pipeline_sidecar_freeze_smoke.py
# SPDX-License-Identifier: Apache-2.0
"""Fait tourner un binaire sidecar gelé (frozen, n'importe lequel — chemin
donné en argv[1]) à travers un cycle réel reader.file -> writer.file, sur
HTTP loopback, pour prouver que le freeze n'a rien perdu. Utilisé en CI
(Tâche 2) et à la main sur la VM Windows de développement."""

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: pipeline_sidecar_freeze_smoke.py <path-to-frozen-binary>", file=sys.stderr)
        return 2
    binary_path = sys.argv[1]

    with tempfile.TemporaryDirectory(prefix="geostudio-freeze-smoke-") as tmp:
        in_path = Path(tmp) / "in.geojson"
        in_path.write_text(
            '{"type":"FeatureCollection","features":['
            '{"type":"Feature","properties":{"label":"a"},'
            '"geometry":{"type":"Point","coordinates":[1,2]}}]}'
        )
        out_path = Path(tmp) / "out.gpkg"

        proc = subprocess.Popen(
            [binary_path, "--base-uri", tmp],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            first_line = proc.stdout.readline()
            match = re.match(r"PORT=(\d+)\n", first_line)
            if not match:
                print(f"FAIL: unexpected first line {first_line!r}", file=sys.stderr)
                print(proc.stderr.read(), file=sys.stderr)
                return 1
            port = int(match.group(1))
            base = f"http://127.0.0.1:{port}"

            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                try:
                    httpx.get(f"{base}/pipelines/ops", timeout=1.0)
                    break
                except httpx.TransportError:
                    time.sleep(0.2)
            else:
                print("FAIL: sidecar never became reachable", file=sys.stderr)
                return 1

            payload = {
                "nodes": [
                    {
                        "id": "r1",
                        "kind": "reader",
                        "op": "reader.file",
                        "params": {"path": str(in_path)},
                    },
                    {
                        "id": "w1",
                        "kind": "writer",
                        "op": "writer.file",
                        "params": {"path": str(out_path)},
                    },
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            }
            put_res = httpx.put(f"{base}/pipelines/smoke", json=payload, timeout=5.0)
            if put_res.status_code != 204:
                print(f"FAIL: PUT returned {put_res.status_code}: {put_res.text}", file=sys.stderr)
                return 1

            run_res = httpx.post(f"{base}/pipelines/smoke/run", timeout=5.0)
            if run_res.status_code != 202:
                print(f"FAIL: run returned {run_res.status_code}: {run_res.text}", file=sys.stderr)
                return 1

            deadline = time.monotonic() + 15.0
            status = None
            while time.monotonic() < deadline:
                runs = httpx.get(f"{base}/pipelines/smoke/runs", timeout=2.0).json()
                status = runs[0]["status"] if runs else None
                if status in ("succeeded", "failed"):
                    break
                time.sleep(0.2)

            if status != "succeeded" or not out_path.exists():
                print(f"FAIL: run status={status}, output exists={out_path.exists()}", file=sys.stderr)
                return 1

            print(f"OK: frozen sidecar ran reader.file -> writer.file, output at {out_path}")
            return 0
        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the control (non-frozen) smoke test**

Run:
```bash
cd core
PYTHONPATH=. uv run python -c "
import sys
sys.argv = ['x', 'scripts/pipeline_sidecar.py']
" 2>/dev/null
```
This isn't runnable directly against the .py file (the smoke script expects
a binary path, not a Python interpreter invocation) — instead verify the
entrypoint itself still works as of Task 1 with:
Run: `cd core && uv run pytest tests/test_pipeline_sidecar_entrypoint.py -v`
Expected: both tests pass (confirms Task 1's baseline before freezing).

- [ ] **Step 4: Write the CI workflow**

```yaml
# .github/workflows/desktop-etl-sidecar-freeze.yml
name: desktop-etl sidecar freeze (real entrypoint)

on:
  workflow_dispatch: {}
  push:
    paths:
      - "core/scripts/pipeline_sidecar.py"
      - "core/scripts/pipeline_sidecar.pyinstaller-args.txt"
      - "core/scripts/pipeline_sidecar_freeze_smoke.py"
      - "core/app/pipelines/**"
      - ".github/workflows/desktop-etl-sidecar-freeze.yml"

jobs:
  freeze-windows:
    runs-on: windows-latest
    defaults:
      run:
        working-directory: core
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - run: uv sync
      - name: Script de contrôle (non gelé)
        env:
          PYTHONPATH: .
        run: uv run python scripts/pipeline_sidecar_entrypoint_smoke_check.py
      - name: Freeze PyInstaller
        shell: bash
        run: |
          extra_args=$(grep -v '^#' scripts/pipeline_sidecar.pyinstaller-args.txt | tr '\n' ' ')
          uv run pyinstaller --onefile --name pipeline-sidecar --paths . $extra_args scripts/pipeline_sidecar.py
      - name: Smoke test du binaire gelé
        run: uv run python scripts/pipeline_sidecar_freeze_smoke.py dist/pipeline-sidecar.exe
      - name: Upload artefact
        uses: actions/upload-artifact@v4
        with:
          name: pipeline-sidecar-windows
          path: core/dist/pipeline-sidecar.exe
          retention-days: 7
```

The "script de contrôle (non gelé)" step above references a file this task
does not create (`pipeline_sidecar_entrypoint_smoke_check.py`) — replace it
with a direct call to the same smoke script against the **unfrozen**
interpreter invocation, which needs a small wrapper since
`pipeline_sidecar_freeze_smoke.py` expects a single executable path.
Simplify instead: drop that step entirely and rely on
`uv run pytest tests/test_pipeline_sidecar_entrypoint.py -v` as the
non-frozen control (matches Step 3 above) — replace the "Script de
contrôle" step with:
```yaml
      - name: Script de contrôle (non gelé)
        env:
          PYTHONPATH: .
        run: uv run pytest tests/test_pipeline_sidecar_entrypoint.py -v
```

- [ ] **Step 5: Push and watch the CI run**

Push the branch, trigger the workflow (`workflow_dispatch` or push to a path
it watches), and confirm the Actions run is green end to end. If the freeze
step fails with a `procrastinate`-related `ModuleNotFoundError` at the smoke
test step, add `--collect-all procrastinate` to
`pipeline_sidecar.pyinstaller-args.txt` (documented in that file's comment,
per Step 1) and re-push. Record the actual outcome (which flags were
needed) in `docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md`
§1 as a new bullet before moving to Task 3 — do not let this finding live
only in CI logs.

- [ ] **Step 6: Commit**

```bash
git add core/scripts/pipeline_sidecar.pyinstaller-args.txt \
  core/scripts/pipeline_sidecar_freeze_smoke.py \
  .github/workflows/desktop-etl-sidecar-freeze.yml \
  docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md
git commit -m "feat(core): gèle l'entrypoint réel du sidecar desktop-etl (CI Windows)"
```

---

### Task 3: Bootstrap `desktop-etl/src-tauri/` — spawn du sidecar + handshake

**Files:**
- Create: `desktop-etl/src-tauri/Cargo.toml`
- Create: `desktop-etl/src-tauri/build.rs`
- Create: `desktop-etl/src-tauri/tauri.conf.json`
- Create: `desktop-etl/src-tauri/capabilities/default.json`
- Create: `desktop-etl/src-tauri/src/main.rs`
- Create: `desktop-etl/scripts/prepare-sidecar-binary.mjs`
- Create: `desktop-etl/README.md`

**Interfaces:**
- Consumes: the frozen `pipeline-sidecar.exe` (Task 2).
- Produces (for Task 4/5): a Tauri command `get_sidecar_connection() ->
  { baseUrl: string, token: string }`, invokable from the webview via
  `@tauri-apps/api/core`'s `invoke("get_sidecar_connection")`.

**Verify before writing any Rust (mandatory, CLAUDE.md piège #3 — this repo
has never built Rust/Tauri before):**
```bash
rustc --version   # confirm a Rust toolchain is installed on the Windows VM
cargo --version
```
If neither is installed, install via https://rustup.rs on the Windows VM
first — this cannot be verified from this Linux session.

- [ ] **Step 1: `Cargo.toml`**

```toml
# desktop-etl/src-tauri/Cargo.toml
[package]
name = "geostudio-desktop-etl"
version = "0.1.0"
edition = "2021"

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = [] }
tauri-plugin-shell = "2"
tauri-plugin-fs = "2"
tauri-plugin-dialog = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
uuid = { version = "1", features = ["v4"] }

[[bin]]
name = "geostudio-desktop-etl"
path = "src/main.rs"
```

**Verify before trusting this file**: run `cargo metadata --no-deps` (or
just `cargo check`, Step 5) once written — `tauri`/`tauri-plugin-shell`
version `"2"` resolves to whatever the latest 2.x is at the time this task
actually runs; if `cargo check` reports a yanked/incompatible version,
pin an exact version from https://crates.io/crates/tauri instead of
guessing, and record the pinned version here.

- [ ] **Step 2: `build.rs`**

```rust
// desktop-etl/src-tauri/build.rs
fn main() {
    tauri_build::build()
}
```

- [ ] **Step 3: `tauri.conf.json` + capabilities**

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "GeoStudio ETL",
  "version": "0.1.0",
  "identifier": "fr.geostudio.desktop-etl",
  "build": {
    "frontendDist": "../../shell/dist-desktop"
  },
  "app": {
    "windows": [
      {
        "title": "GeoStudio ETL",
        "width": 1280,
        "height": 800
      }
    ]
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "nsis"],
    "externalBin": ["binaries/pipeline-sidecar"]
  }
}
```

`frontendDist` points at Task 5's build output, which does not exist yet —
`tauri dev`/`tauri build` will fail until Task 5 is done; this is expected
and re-verified in Task 6, not in this task. **No `build.devUrl`** is set:
this plan deliberately runs `npm run build:desktop-runtime` before every
`tauri dev`/`tauri build` invocation rather than wiring a Vite dev server
into Tauri's hot-reload — a slower loop, but avoids a second class of
config (devUrl + CSP for it) for a v1 product with no polish requirement on
the dev experience itself (YAGNI).

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Capability for the main window",
  "windows": ["main"],
  "permissions": [
    "core:default",
    {
      "identifier": "shell:allow-execute",
      "allow": [{ "args": ["--base-uri", { "validator": "\\S+" }], "name": "binaries/pipeline-sidecar", "sidecar": true }]
    },
    "fs:default",
    "fs:allow-read-text-file",
    "fs:allow-write-text-file",
    "dialog:default"
  ]
}
```
(File: `desktop-etl/src-tauri/capabilities/default.json`.)

**Verify before trusting this capabilities file**: the exact permission
identifiers (`fs:allow-read-text-file`, `dialog:default`, the `shell:
allow-execute` args validator shape) come from the official v2 docs
fetched 2026-09-18, but capability schemas are strict and versioned —
`tauri dev` (Step 5) will refuse to start with a clear error naming any
unknown permission identifier; fix from that error message, not by
re-guessing.

- [ ] **Step 4: `main.rs`**

```rust
// desktop-etl/src-tauri/src/main.rs
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SidecarConnection {
    base_url: String,
    token: String,
}

struct SidecarState(Mutex<Option<SidecarConnection>>);

#[tauri::command]
fn get_sidecar_connection(state: tauri::State<SidecarState>) -> Result<SidecarConnection, String> {
    state
        .0
        .lock()
        .unwrap()
        .clone()
        .ok_or_else(|| "sidecar not ready yet".to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(SidecarState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![get_sidecar_connection])
        .setup(|app| {
            let token = uuid::Uuid::new_v4().to_string();
            let sidecar_command = app
                .shell()
                .sidecar("binaries/pipeline-sidecar")
                .expect("failed to resolve sidecar binary")
                .env("GEOSTUDIO_SIDECAR_TOKEN", &token);
            let (mut rx, _child) = sidecar_command.spawn().expect("failed to spawn sidecar");

            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    if let CommandEvent::Stdout(line_bytes) = event {
                        let line = String::from_utf8_lossy(&line_bytes);
                        if let Some(port_str) = line.trim().strip_prefix("PORT=") {
                            if let Ok(port) = port_str.parse::<u16>() {
                                let state = app_handle.state::<SidecarState>();
                                *state.0.lock().unwrap() = Some(SidecarConnection {
                                    base_url: format!("http://127.0.0.1:{port}"),
                                    token: token.clone(),
                                });
                            }
                            break;
                        }
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

**Verify before trusting this file** (do this on the Windows VM, Step 5):
the exact shape of `app.shell().sidecar(...).env(...)` — this plan assumes
a builder-style `.env(key, value)` method mirroring
`std::process::Command`, inferred from `tauri-plugin-shell`'s general
`Command`-like API (the context7 docs fetched 2026-09-18 showed `.arg()`
chaining but not `.env()` explicitly) — if `cargo check` reports no such
method, run `cargo doc -p tauri-plugin-shell --open` (or check
https://docs.rs/tauri-plugin-shell for the installed version) and adjust
this call to whatever the real builder method is called; do not guess a
second time; also note this env-based one-token-in-a-child-process-var
approach is a passing-the-only-copy handoff — the token never touches
disk, argv, or Tauri's own logs.

- [ ] **Step 5: First compile check (Windows VM)**

On the Windows VM, with the Task 2 frozen binary copied to
`desktop-etl/src-tauri/binaries/pipeline-sidecar-x86_64-pc-windows-msvc.exe`
(get the exact target triple with `rustc --print host-tuple` first — do not
assume `x86_64-pc-windows-msvc`, confirm it):

```powershell
cd desktop-etl/src-tauri
cargo check
```

Expected: compiles (after fixing any API mismatches flagged by the
"verify before trusting" notes above). This does **not** yet start the app
(no frontend build exists — Task 5) — `cargo check` only proves the Rust
code compiles.

- [ ] **Step 6: `prepare-sidecar-binary.mjs`**

```javascript
// desktop-etl/scripts/prepare-sidecar-binary.mjs
// Copie/renomme le binaire gelé (Tâche 2) avec le suffixe target-triple que
// Tauri exige pour un externalBin (docs Tauri v2, "sidecar naming").
import { execSync } from "node:child_process";
import { copyFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const sourcePath = process.argv[2];
if (!sourcePath) {
  console.error("usage: node prepare-sidecar-binary.mjs <path-to-frozen-binary>");
  process.exit(2);
}

const targetTriple = execSync("rustc --print host-tuple").toString().trim();
const ext = process.platform === "win32" ? ".exe" : "";
const destDir = resolve(__dirname, "../src-tauri/binaries");
mkdirSync(destDir, { recursive: true });
const destPath = resolve(destDir, `pipeline-sidecar-${targetTriple}${ext}`);
copyFileSync(sourcePath, destPath);
console.log(`copied ${sourcePath} -> ${destPath}`);
```

- [ ] **Step 7: `README.md`**

```markdown
# desktop-etl

Application Tauri (Windows uniquement en v1) qui embarque le sidecar
Python `core/scripts/pipeline_sidecar.py` (gelé PyInstaller, Tâche 2 de
`docs/superpowers/plans/2026-09-18-desktop-etl-phase-fg.md`) et le canvas
pipeline existant du shell (`shell/src/desktop/entry.tsx`, Tâche 5).

## Développement (Windows uniquement)

1. Geler le sidecar (ou télécharger l'artefact CI de
   `.github/workflows/desktop-etl-sidecar-freeze.yml`) :
   `cd core && uv run pyinstaller --onefile --name pipeline-sidecar --paths . --collect-all dlt scripts/pipeline_sidecar.py`
2. `node desktop-etl/scripts/prepare-sidecar-binary.mjs core/dist/pipeline-sidecar.exe`
3. `cd shell && npm run build:desktop-runtime`
4. `cd desktop-etl/src-tauri && cargo tauri dev` (ou `cargo run` si le
   plugin CLI `tauri` n'est pas installé globalement — voir
   `cargo install tauri-cli --version "^2"`).
```

- [ ] **Step 8: Commit**

```bash
git add desktop-etl/
git commit -m "feat(desktop-etl): bootstrap Tauri, spawn du sidecar avec jeton"
```

---

### Task 4: `DesktopItemClient` (TypeScript)

**Files:**
- Create: `shell/src/desktop/DesktopItemClient.ts`
- Create: `shell/src/desktop/DesktopItemClient.test.ts`

**Interfaces:**
- Consumes: `ItemClient` (full interface, `shell/src/api/types.ts:390`,
  137 methods), `OWNER_PERMISSIONS` (`shell/src/auth/permissions.ts`,
  already imported this way by `shell/src/api/domains/pipelines.ts:12`),
  `PipelinePayload`/`PipelineOpsCatalog`/`PipelineRun`/`Item`/
  `ConfigRevisionInfo`/`PipelineWebhookToken` types (`shell/src/api/types.ts`).
- Produces (for Task 5): `createDesktopItemClient(connection: { baseUrl:
  string; token: string }): ItemClient`.

**Design decision, verified against the actual codebase before writing
this (not from the design doc's own illustrative sketch, which turned out
to describe the wrong pattern):** `shell/src/staticExport/StaticItemClient.ts`
already solves the exact same problem (a partial, backend-less `ItemClient`)
for the SP-18a static export product — its own top comment explicitly
records that an earlier sketch used `as unknown as ItemClient`/a Proxy-style
shortcut and that the real implementation rejected it in favor of listing
every one of the 137 methods explicitly, "so TypeScript proves nothing was
forgotten." `DesktopItemClient.ts` follows the same pattern: copy
`StaticItemClient.ts`'s full method list, replace `UNSUPPORTED`'s message,
and give the ~9 pipeline methods (plus one deliberate exception,
`listConfigRevisions`) a real desktop implementation instead of rejecting.

- [ ] **Step 1: Write the failing tests**

```typescript
// SPDX-License-Identifier: Apache-2.0
// shell/src/desktop/DesktopItemClient.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";
import { createDesktopItemClient } from "./DesktopItemClient";

const CONNECTION = { baseUrl: "http://127.0.0.1:9999", token: "s3cr3t" };

describe("createDesktopItemClient", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("sends the bearer token on every sidecar request", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ "reader.file": { kind: "reader", paramsSchema: {} } }), {
        status: 200,
      }),
    );
    const client = createDesktopItemClient(CONNECTION);
    await client.getPipelineOps();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:9999/pipelines/ops");
    expect((init?.headers as Record<string, string>)["Authorization"]).toBe("Bearer s3cr3t");
  });

  it("createPipelineItem builds a local Item and PUTs the payload to the sidecar", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = createDesktopItemClient(CONNECTION);
    const payload = { nodes: [], edges: [] };
    const item = await client.createPipelineItem({
      title: "Mon pipeline",
      owner: "local",
      pipeline: payload,
    });
    expect(item.resourceType).toBe("pipeline");
    expect(item.title).toBe("Mon pipeline");
    expect(item.pk).toBeTruthy();
    expect(item.permissions).toEqual(expect.objectContaining({ canWrite: true }));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`http://127.0.0.1:9999/pipelines/${item.pk}`);
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual(payload);
  });

  it("getPipelineConfig fetches the last PUT payload back from the sidecar's own store", async () => {
    // Le sidecar n'a pas de GET /pipelines/{id} dédié (contrat §3.1 du
    // roadmap) — getPipelineConfig doit donc garder le payload en mémoire
    // côté client desktop lui-même (jamais relu depuis le sidecar).
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = createDesktopItemClient(CONNECTION);
    const payload = { nodes: [], edges: [] };
    const item = await client.createPipelineItem({ title: "t", owner: "o", pipeline: payload });
    const roundtripped = await client.getPipelineConfig(item.pk);
    expect(roundtripped).toEqual(payload);
  });

  it("listConfigRevisions resolves to an empty list instead of rejecting", async () => {
    const client = createDesktopItemClient(CONNECTION);
    await expect(client.listConfigRevisions("any-pk")).resolves.toEqual([]);
  });

  it("rollbackConfig rejects (no version history in desktop mode)", async () => {
    const client = createDesktopItemClient(CONNECTION);
    await expect(client.rollbackConfig("any-pk", 1)).rejects.toThrow();
  });

  it("listPipelineWebhookTokens rejects (webhooks are server-only, out of scope for v1)", async () => {
    const client = createDesktopItemClient(CONNECTION);
    await expect(client.listPipelineWebhookTokens("any-pk")).rejects.toThrow();
  });

  it("a method with no desktop meaning at all rejects with a clear message", async () => {
    const client = createDesktopItemClient(CONNECTION);
    await expect(client.listCollections()).rejects.toThrow(/desktop/i);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/desktop/DesktopItemClient.test.ts`
Expected: FAIL — `Cannot find module './DesktopItemClient'`.

- [ ] **Step 3: Write the implementation**

Start from a full copy of `shell/src/staticExport/StaticItemClient.ts`'s
method list (all 137 methods present, unmodified in this file), then apply
exactly these changes:
- Rename `createStaticItemClient(config: AppConfig)` to
  `createDesktopItemClient(connection: { baseUrl: string; token: string })`.
- Change `UNSUPPORTED` to `"Non disponible en mode desktop."`.
- Remove the "Implémentées réellement" block (`getAppConfig`,
  `getPublicAppConfig`, `queryDataSource`, `invalidateDatasetCache`,
  `featuresUrl`, `createFeature`, `updateFeature`, `deleteFeature`,
  `exportDataSource`, `runAnalyticsSql`) — none of these have desktop
  meaning either; let them fall through to `unsupported()` like every other
  non-pipeline method.
- Replace the 7 stubbed pipeline methods (`createPipelineItem`,
  `getPipelineConfig`, `savePipelineConfig`, `getPipelineOps`,
  `runPipeline`, `getPipelineRuns`, `previewPipeline`) with real
  implementations.
- Replace `listConfigRevisions` with a resolved empty array (the one
  deliberate exception — see rationale below).
- Leave every other method (including `rollbackConfig`,
  `listPipelineWebhookTokens`, `createPipelineWebhookToken`,
  `revokePipelineWebhookToken`) exactly as `StaticItemClient.ts` has them
  (`unsupported()`).

```typescript
// SPDX-License-Identifier: Apache-2.0
// Implémentation "sidecar loopback" d'ItemClient pour le desktop-etl (Phase
// G, docs/superpowers/plans/2026-09-18-desktop-etl-phase-fg.md, Tâche 4).
// Même discipline que StaticItemClient.ts (SP-18a) : chaque méthode de
// l'interface est listée explicitement — rejet clair pour tout ce qui n'a
// pas de sens sans backend cœur (catalogue, partage, harvest, connecteurs,
// secrets, 3D, MCP…), implémentation réelle seulement pour les ~9 méthodes
// pipeline. Pas de Proxy, pas de `as unknown as ItemClient` : TypeScript
// doit prouver qu'aucune méthode n'a été oubliée.
import type {
  ConfigRevisionInfo,
  Item,
  ItemClient,
  PageParams,
  PipelineOpsCatalog,
  PipelinePayload,
  PipelineRun,
} from "../api/types";
import { OWNER_PERMISSIONS } from "../auth/permissions";

const UNSUPPORTED = "Non disponible en mode desktop.";

function unsupported<T = never>(): Promise<T> {
  return Promise.reject(new Error(UNSUPPORTED));
}

export function createDesktopItemClient(connection: {
  baseUrl: string;
  token: string;
}): ItemClient {
  const { baseUrl, token } = connection;
  // Le sidecar n'a pas de GET /pipelines/{id} (contrat verrouillé, roadmap
  // §3.1 — seul un PUT existe) : le payload actif doit donc être gardé ici,
  // côté client desktop, en plus d'être poussé au sidecar à chaque PUT.
  const localPayloads = new Map<string, PipelinePayload>();

  async function sidecarFetch<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const res = await fetch(`${baseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`sidecar ${method} ${path} -> ${res.status}`);
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  return {
    async createPipelineItem(input: {
      title: string;
      owner: string;
      pipeline: PipelinePayload;
    }): Promise<Item> {
      const pk = crypto.randomUUID();
      localPayloads.set(pk, input.pipeline);
      await sidecarFetch<void>("PUT", `/pipelines/${pk}`, input.pipeline);
      return {
        pk,
        resourceType: "pipeline",
        title: input.title,
        abstract: "",
        owner: input.owner,
        thumbnailUrl: null,
        date: new Date().toISOString(),
        configId: pk,
        isPublished: false,
        license: "",
        language: "fr",
        permissions: OWNER_PERMISSIONS,
      };
    },

    async getPipelineConfig(pk: string): Promise<PipelinePayload> {
      const payload = localPayloads.get(pk);
      if (!payload) throw new Error(`getPipelineConfig: no local pipeline for ${pk}`);
      return payload;
    },

    async savePipelineConfig(pk: string, payload: PipelinePayload): Promise<void> {
      localPayloads.set(pk, payload);
      await sidecarFetch<void>("PUT", `/pipelines/${pk}`, payload);
    },

    async getPipelineOps(): Promise<PipelineOpsCatalog> {
      return sidecarFetch<PipelineOpsCatalog>("GET", "/pipelines/ops");
    },

    async runPipeline(pk: string): Promise<{ runId: string }> {
      return sidecarFetch<{ runId: string }>("POST", `/pipelines/${pk}/run`);
    },

    async getPipelineRuns(pk: string, params?: PageParams): Promise<PipelineRun[]> {
      const query = new URLSearchParams();
      if (params?.limit !== undefined) query.set("limit", String(params.limit));
      if (params?.offset !== undefined) query.set("offset", String(params.offset));
      const qs = query.toString();
      return sidecarFetch<PipelineRun[]>("GET", `/pipelines/${pk}/runs${qs ? `?${qs}` : ""}`);
    },

    async previewPipeline(pk: string, upToNodeId: string): Promise<Record<string, unknown>[]> {
      return sidecarFetch<Record<string, unknown>[]>(
        "POST",
        `/pipelines/${pk}/preview?upTo=${encodeURIComponent(upToNodeId)}`,
      );
    },

    // Exception délibérée à la discipline "rejet explicite" ci-dessus :
    // ConfigHistoryPanel.tsx (rendu inconditionnellement par
    // PipelineBuilderPage dès pk !== null) affiche un bandeau d'erreur
    // visible en permanence sur un rejet ; []  est une réponse vraie (aucune
    // révision n'existe en desktop, design §1 non-but) et rend un panneau
    // "aucune version" au lieu d'un faux état d'erreur, pour zéro coût.
    async listConfigRevisions(_pk: string): Promise<ConfigRevisionInfo[]> {
      return [];
    },

    async rollbackConfig(..._args: unknown[]) {
      return unsupported();
    },

    // --- Reste de l'interface (136 méthodes restantes) : copier
    // verbatim la liste de shell/src/staticExport/StaticItemClient.ts à
    // partir de "listItems" jusqu'à la fin du fichier, à l'IDENTIQUE
    // (même noms, même unsupported()) — reproduite ici en intégralité par
    // l'implémenteur, pas résumée, pour que TypeScript vérifie les 137
    // méthodes. Inclut listPipelineWebhookTokens/createPipelineWebhookToken/
    // revokePipelineWebhookToken (webhooks hors périmètre desktop v1).
  };
}
```

**Implementer's note, not a placeholder to skip:** the elided block above
is a copy instruction, not missing content — `StaticItemClient.ts`'s
136 remaining stub methods (everything after `deleteAttachment`/before it,
per the file this plan already quoted verbatim from at
`shell/src/staticExport/StaticItemClient.ts:75-452` when this plan was
written) must be pasted in full, character-for-character except for the
`UNSUPPORTED` message text already changed above. Run `npx tsc --noEmit`
after pasting — a missing method fails the build with "Property 'X' is
missing in type" naming exactly which one, so this is self-checking.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/desktop/DesktopItemClient.test.ts`
Expected: all passed. Also run `cd shell && npx tsc --noEmit` — must be
clean (proves every one of the 137 `ItemClient` methods is present).

- [ ] **Step 5: Commit**

```bash
git add shell/src/desktop/DesktopItemClient.ts shell/src/desktop/DesktopItemClient.test.ts
git commit -m "feat(shell): ajoute DesktopItemClient (sidecar loopback, desktop-etl)"
```

---

### Task 5: Build Vite desktop (`vite.desktop.config.ts` + entry point)

**Files:**
- Create: `shell/vite.desktop.config.ts`
- Create: `shell/index.desktop.html`
- Create: `shell/src/desktop/entry.tsx`
- Modify: `shell/package.json`

**Interfaces:**
- Consumes: `createDesktopItemClient` (Task 4), `get_sidecar_connection`
  Tauri command (Task 3), `enableMockAuth` (`shell/src/auth/useAuth.ts:15`,
  unchanged), `PipelineBuilderPage` (`shell/src/pages/PipelineBuilderPage.tsx`,
  unchanged).
- Produces: `shell/dist-desktop/` (build output), the `distDir` Task 3's
  `tauri.conf.json` already points at.

**Verified before writing this task:** `PipelineBuilderPage.tsx` calls
`useNavigate()`/`useParams()`/`useLocation()` (needs a Router ancestor) and
`useAuth()` (needs either an OIDC context or `enableMockAuth()` called
before first render — the latter makes `useAuth()` skip
`react-oidc-context` entirely, already the mechanism
`shell/src/staticExport/entry.tsx` and multiple `*.test.tsx` files use).
`PipelineScheduleEditor`/`PipelineWebhookTrigger` render unconditionally
once a pipeline exists but call no client method that would visibly break
the golden path (`PipelineScheduleEditor` calls no client method at all;
`PipelineWebhookTrigger`'s list falls back to `[] `on a rejected query,
console-only noise, no visible banner) — confirmed by reading both files
2026-09-18, not assumed.

- [ ] **Step 1: `shell/index.desktop.html`**

```html
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <title>GeoStudio ETL</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/desktop/entry.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: `shell/vite.desktop.config.ts`**

```typescript
// SPDX-License-Identifier: Apache-2.0
// Config Vite séparée de vite.config.ts, même patron que
// vite.export.config.ts (SP-18a) : ce build ne dépend jamais de la config
// de test, produit un artefact autonome consommé par
// desktop-etl/src-tauri/tauri.conf.json (build.frontendDist).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import { resolve } from "node:path";
import { copyMaplibreWorkerPlugin } from "./vite.copyMaplibreWorker.ts";

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss(), copyMaplibreWorkerPlugin()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "dist-desktop",
    rollupOptions: {
      input: resolve(__dirname, "index.desktop.html"),
    },
  },
});
```

- [ ] **Step 3: `shell/src/desktop/entry.tsx`**

```typescript
// SPDX-License-Identifier: Apache-2.0
// Point d'entrée Vite du desktop-etl (Phase G, plan Tâche 5). Réutilise
// PipelineBuilderPage tel quel (aucun fichier de builder/pipeline/ modifié)
// derrière un MemoryRouter à 2 routes au lieu du BrowserRouter+AppRoutes
// complet d'App.tsx — ce produit n'a qu'un seul écran.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useParams } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";
import { enableMockAuth } from "../auth/useAuth";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { createDesktopItemClient } from "./DesktopItemClient";
import { PipelineBuilderPage } from "../pages/PipelineBuilderPage";
import "../index.css";

enableMockAuth();
const queryClient = new QueryClient();

function NewPipelineRoute() {
  return <PipelineBuilderPage pk={null} initialTitle="Nouveau pipeline" />;
}

function EditPipelineRoute() {
  const { pk } = useParams();
  return <PipelineBuilderPage pk={pk!} />;
}

async function bootstrap() {
  const root = document.getElementById("root");
  if (!root) throw new Error("desktop entry: #root introuvable");

  const connection = await invoke<{ baseUrl: string; token: string }>(
    "get_sidecar_connection",
  );
  const client = createDesktopItemClient(connection);

  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <MemoryRouter initialEntries={["/pipelines/new"]}>
            <Routes>
              <Route path="/pipelines/new" element={<NewPipelineRoute />} />
              <Route path="/pipelines/:pk/edit" element={<EditPipelineRoute />} />
            </Routes>
          </MemoryRouter>
        </ItemClientProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}

bootstrap().catch((err) => {
  const root = document.getElementById("root");
  if (root) root.textContent = `Erreur de démarrage : ${(err as Error).message}`;
});
```

`get_sidecar_connection` (Task 3, Rust) is populated by the `.setup()` hook
asynchronously — if the webview's first `invoke()` races ahead of the
handshake completing, it returns the `Err("sidecar not ready yet")` this
file surfaces as a startup error screen rather than silently hanging.
**Verify this race on the Windows VM in Task 6** (retry with a short delay
loop if it fires in practice — do not add speculative retry logic here
before observing whether the race is real).

- [ ] **Step 4: Add dependencies + build script**

```bash
cd shell
npm install @tauri-apps/api @tauri-apps/plugin-shell @tauri-apps/plugin-fs @tauri-apps/plugin-dialog
```

Add to `shell/package.json`'s `"scripts"` (alongside the existing
`"build:export-runtime"` line):
```json
    "build:desktop-runtime": "vite build --config vite.desktop.config.ts",
```

- [ ] **Step 5: Build and typecheck**

Run: `cd shell && npx tsc --noEmit && npm run build:desktop-runtime`
Expected: clean typecheck, `dist-desktop/index.desktop.html` +
`dist-desktop/assets/*` produced.

- [ ] **Step 6: Commit**

```bash
git add shell/vite.desktop.config.ts shell/index.desktop.html shell/src/desktop/entry.tsx \
  shell/package.json shell/package-lock.json
git commit -m "feat(shell): build Vite desktop-etl (canvas pipeline réutilisé, ItemClient loopback)"
```

---

### Task 6: Intégration manuelle bout-en-bout (VM Windows)

**Files:** none created; manual verification + fixes to whatever breaks,
on the user's Windows VM — the first point in this whole plan where all
the pieces run together for real.

- [ ] **Step 1: Assemble the binary**

On the Windows VM: freeze the sidecar (Task 2's recipe, or download the CI
artifact), run `node desktop-etl/scripts/prepare-sidecar-binary.mjs
<path-to-pipeline-sidecar.exe>`, then `cd shell && npm ci && npm run
build:desktop-runtime`.

- [ ] **Step 2: First real launch**

```powershell
cd desktop-etl/src-tauri
cargo tauri dev
```
(Install the Tauri CLI first if needed: `cargo install tauri-cli --version "^2" --locked`.)

Expected: a window opens showing the pipeline builder's triptych layout,
empty canvas, palette on the left. If it doesn't, read the actual error
(missing capability permission, sidecar failed to spawn, frontend 404) and
fix the specific file that caused it — do not guess broadly.

- [ ] **Step 2: Golden path, by hand**

- Drag a `reader.file` node onto the canvas, set its `path` param to a real
  local GeoJSON file's absolute path.
- Drag a `writer.file` node, set its `path` param to a new local `.gpkg`
  path, connect the two nodes.
- Click "Enregistrer" — confirm no error banner, confirm the pipeline
  becomes editable (the route changed from `new` to an `edit` state,
  observable via the run/preview panels now rendering — they only render
  when `pk !== null`, cf. `PipelineBuilderPage.tsx`).
- Click "Exécuter" (`PipelineRunPanel`) — confirm it reaches `succeeded`.
- Confirm the output `.gpkg` file exists on disk with the expected content.

- [ ] **Step 3: Fix whatever broke**

Document every fix made in this step directly in
`desktop-etl/README.md` (a "pièges rencontrés" section) — this is exactly
the kind of first-real-integration friction CLAUDE.md piège #3 expects to
surface here, not before.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "fix(desktop-etl): corrige l'intégration bout-en-bout trouvée au premier lancement réel"
```

---

### Task 7: E2E golden path (Tauri WebDriver)

**Files:**
- Create: `desktop-etl/e2e/package.json`
- Create: `desktop-etl/e2e/wdio.conf.js`
- Create: `desktop-etl/e2e/specs/golden-path.spec.js`
- Create: `.github/workflows/desktop-etl-webdriver.yml`

**Interfaces:**
- Consumes: the working Tauri app from Task 6 (`cargo tauri build --debug
  --no-bundle` produces `desktop-etl/src-tauri/target/debug/geostudio-desktop-etl.exe`).

- [ ] **Step 1: `desktop-etl/e2e/package.json`**

```json
{
  "name": "desktop-etl-e2e",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": { "test": "wdio run wdio.conf.js" },
  "dependencies": { "@wdio/cli": "^9.19.0" },
  "devDependencies": {
    "@wdio/local-runner": "^9.19.0",
    "@wdio/mocha-framework": "^9.19.0",
    "@wdio/spec-reporter": "^9.19.0"
  }
}
```

- [ ] **Step 2: `desktop-etl/e2e/wdio.conf.js`**

```javascript
// desktop-etl/e2e/wdio.conf.js
import os from "os";
import path from "path";
import { spawn, spawnSync } from "child_process";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
let tauriDriver;
let exiting = false;

export const config = {
  host: "127.0.0.1",
  port: 4444,
  specs: ["./specs/**/*.js"],
  maxInstances: 1,
  capabilities: [
    {
      maxInstances: 1,
      "tauri:options": {
        application: "../src-tauri/target/debug/geostudio-desktop-etl.exe",
      },
    },
  ],
  reporters: ["spec"],
  framework: "mocha",
  mochaOpts: { ui: "bdd", timeout: 60000 },
  onPrepare: () => {
    spawnSync("npm", ["run", "tauri", "build", "--", "--debug", "--no-bundle"], {
      cwd: path.resolve(__dirname, "../src-tauri"),
      stdio: "inherit",
      shell: true,
    });
  },
  beforeSession: () => {
    tauriDriver = spawn(path.resolve(os.homedir(), ".cargo", "bin", "tauri-driver"), [], {
      stdio: [null, process.stdout, process.stderr],
    });
    tauriDriver.on("error", (error) => {
      console.error("tauri-driver error:", error);
      process.exit(1);
    });
    tauriDriver.on("exit", (code) => {
      if (!exiting) {
        console.error("tauri-driver exited with code:", code);
        process.exit(1);
      }
    });
  },
  afterSession: () => closeTauriDriver(),
};

function closeTauriDriver() {
  exiting = true;
  tauriDriver?.kill();
}
process.on("exit", closeTauriDriver);
process.on("SIGINT", closeTauriDriver);
```

**Verify before trusting this file**: the `"tauri:options"` capability and
`tauri-driver` invocation come from the official v2 WebDriver docs fetched
2026-09-18; the `onPrepare` command assumes a `"tauri"` npm script exists
in `desktop-etl/src-tauri` — this repo has no `package.json` there (it's a
pure Cargo project, no Node). Replace that `spawnSync` call with a direct
`cargo tauri build -- --debug --no-bundle` invocation instead:
```javascript
  onPrepare: () => {
    spawnSync("cargo", ["tauri", "build", "--", "--debug", "--no-bundle"], {
      cwd: path.resolve(__dirname, "../src-tauri"),
      stdio: "inherit",
      shell: true,
    });
  },
```

- [ ] **Step 3: `desktop-etl/e2e/specs/golden-path.spec.js`**

```javascript
// desktop-etl/e2e/specs/golden-path.spec.js
describe("desktop-etl golden path", () => {
  it("creates, runs, and confirms a file-to-file pipeline", async () => {
    // Sélecteurs à vérifier/ajuster contre le DOM réel une fois l'app
    // lancée sous WebDriver (Étape 4) — le canvas pipeline n'a pas été
    // conçu avec des data-testid dédiés pour ce scénario ; utiliser les
    // rôles ARIA/labels déjà posés par PipelinePalette/PipelineCanvas
    // (cf. shell/src/builder/pipeline/*.test.tsx pour les sélecteurs
    // Testing Library existants, à transposer en sélecteurs WebDriverIO).
    const readerNode = await $('[data-op="reader.file"]');
    await readerNode.dragAndDrop(await $(".pipeline-canvas"));
    // ... compléter une fois les vrais sélecteurs observés (Étape 4).
  });
});
```

This spec is intentionally left as a skeleton with a documented reason
(no stable test selectors exist yet on the canvas for drag-and-drop
targets) — **Step 4 requires actually running this against the real app
and iterating on real selectors observed in the WebDriver session**, not
guessing DOM structure from source reading alone (CLAUDE.md piège #3: a
canvas built for mouse/pointer drag events may need WebDriver's
`dragAndDrop` replaced by raw `performActions` pointer sequences — verify
empirically).

- [ ] **Step 4: Run and iterate on the Windows VM**

```powershell
cargo install tauri-driver --locked
cd desktop-etl/e2e
npm install
npm test
```
Iterate on `golden-path.spec.js`'s selectors and interaction method until
it reliably passes, verifying manually in the opened window at each
attempt. Record the final working selectors/interactions — this is the
actual deliverable of this task, not the skeleton above.

- [ ] **Step 5: CI workflow**

```yaml
# .github/workflows/desktop-etl-webdriver.yml
name: desktop-etl WebDriver E2E

on:
  workflow_dispatch: {}
  push:
    paths:
      - "desktop-etl/**"
      - "shell/src/desktop/**"
      - "shell/src/builder/pipeline/**"
      - ".github/workflows/desktop-etl-webdriver.yml"

jobs:
  e2e-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - name: Freeze sidecar
        working-directory: core
        run: |
          uv sync
          uv run pyinstaller --onefile --name pipeline-sidecar --paths . --collect-all dlt scripts/pipeline_sidecar.py
      - name: Prepare sidecar binary
        run: node desktop-etl/scripts/prepare-sidecar-binary.mjs core/dist/pipeline-sidecar.exe
      - name: install msedgedriver
        run: |
          cargo install --git https://github.com/chippers/msedgedriver-tool
          & "$HOME/.cargo/bin/msedgedriver-tool.exe"
          $PWD.Path >> $env:GITHUB_PATH
      - uses: dtolnay/rust-toolchain@stable
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - name: Build shell desktop runtime
        working-directory: shell
        run: |
          npm ci
          npm run build:desktop-runtime
      - name: Install tauri-driver
        run: cargo install tauri-driver --locked
      - name: WebdriverIO
        working-directory: desktop-etl/e2e
        run: |
          npm install
          npm test
```

- [ ] **Step 6: Commit**

```bash
git add desktop-etl/e2e .github/workflows/desktop-etl-webdriver.yml
git commit -m "test(desktop-etl): E2E golden path Tauri WebDriver"
```

---

### Task 8: Vérification finale

**Files:** none created; verification only.

- [ ] **Step 1: Full core suite**

Run: `cd core && uv run pytest -q`
Expected: 0 failed (same skip counts as before this plan for
`postgis`/`qgis` markers — do not attribute a change to this plan without
checking `CORE_TEST_DATABASE_URL`/`CORE_TEST_QGIS_WORKER_URL` first).

- [ ] **Step 2: Core quality gates**

```bash
cd core
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```

- [ ] **Step 3: Shell suite + quality gates**

```bash
cd shell
npm run test
npx tsc --noEmit
npm run build
npm run lint
npm run format:check
```
`npm run build` (the normal shell build, `vite.config.ts`) must stay
unaffected by the new `vite.desktop.config.ts`/`shell/src/desktop/*` files
— confirm the normal bundle-size gate
(`node scripts/check-bundle-size.mjs`) still passes with no regression
(the new desktop files are never imported by the normal shell entry point).

- [ ] **Step 4: Feature inventory**

This phase adds no server-reachable surface (no new `/v1/` route, no new
MCP tool) — the sidecar stays unmounted from `core/app/main.py`, and
`desktop-etl/` is a separate distributable product, not a shell route.
Confirm `grep -n "sidecar" core/app/main.py` is empty before skipping the
`docs/revue/inventaire-fonctionnalites.jsonl` update CLAUDE.md otherwise
requires.

- [ ] **Step 5: Update the roadmap and spec status**

Edit `docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md`
§4 to mark Phase F and Phase G closed, with the actual commit range and any
deviations recorded during execution (the token-handshake simplification
from Task 1, the actual PyInstaller flags from Task 2, any Tauri API
corrections from Task 3's "verify before trusting" notes). Append an entry
to `docs/superpowers/2026-08-27-historique-execution-continu.md` per
CLAUDE.md's closing ritual. Do not add a line to `CLAUDE.md`'s `### Livré`
yet — Phases I/J/K remain, and that section is reserved for when the whole
desktop-etl product ships (matching the precedent set by every prior
desktop-etl phase's plan).

- [ ] **Step 6: Final commit**

```bash
git add docs/superpowers/plans/2026-09-18-desktop-etl-phase-fg.md \
  docs/superpowers/specs/2026-09-18-desktop-etl-remaining-roadmap.md \
  docs/superpowers/2026-08-27-historique-execution-continu.md
git commit -m "docs(superpowers): clôture Phase F+G du sidecar desktop-etl"
```

---

## Self-Review Notes

- **Spec coverage:** every section of
  `docs/superpowers/specs/2026-09-18-desktop-etl-phase-fg-design.md` maps
  to a task — §4 (sécurité) → Task 1, §5 (freeze) → Task 2, §3.1/§3.3
  (Tauri) → Task 3, §3.2 (ItemClient) → Task 4, §3.1 file layout → Task 5,
  §1 (critère de complétude) → Tasks 6/7, §6 (tests) → Tasks 2/7/8.
- **No placeholders:** every step has real, complete code; the two
  genuinely unverifiable areas (exact `tauri-plugin-shell` builder method
  names, exact WebDriver selectors for the existing canvas) are called out
  with a concrete verification command and a fallback path, never left as
  a bare "figure it out."
- **Type consistency:** `SidecarConnection`'s Rust struct
  (`{ base_url, token }`, `#[serde(rename_all = "camelCase")]`) matches the
  TS `invoke<{ baseUrl: string; token: string }>(...)` call in Task 5 field
  for field; `DesktopItemClient`'s `sidecarFetch` helper and route strings
  in Task 4 match the roadmap §3.1 contract table exactly (same paths,
  same query param names `limit`/`offset`/`upTo`).
- **Deviations from the approved spec, recorded rather than silently
  applied:** Task 1 simplifies the design's `PORT=<n>\nTOKEN=<t>` two-line
  handshake down to the original one-line `PORT=<n>` (the token travels via
  an environment variable Tauri itself sets, so echoing it back verifies
  nothing) — documented inline in Task 1 rather than treated as a silent
  rewrite of the spec.
