### Task 2: `build_bundle_zip` gains an optional `connection` payload

**Files:**
- Modify: `core/app/appexport/bundler.py`
- Modify: `core/tests/test_appexport_bundler.py`

**Interfaces:**
- Consumes: unchanged.
- Produces: `build_bundle_zip(config: BuilderConfig, *, runtime_dir: str, connection: dict | None = None) -> bytes`. When `connection` is provided, the zip additionally contains `geostudio-connection.json` (plain `json.dumps(connection)`) at the zip root. Default `None` preserves SP-18a's exact existing behavior byte-for-byte (no such file, existing tests untouched).

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_appexport_bundler.py` (existing two tests stay exactly as-is above this):

```python


def test_bundle_includes_connection_json_when_provided(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.export.html").write_text("<html></html>")

    zip_bytes = build_bundle_zip(
        _config(), runtime_dir=str(runtime_dir), connection={"coreUrl": "https://core.example.org"},
    )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "geostudio-connection.json" in zf.namelist()
        payload = zf.read("geostudio-connection.json").decode("utf-8")
        assert '"coreUrl"' in payload and "https://core.example.org" in payload


def test_bundle_omits_connection_json_by_default(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.export.html").write_text("<html></html>")

    zip_bytes = build_bundle_zip(_config(), runtime_dir=str(runtime_dir))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert "geostudio-connection.json" not in zf.namelist()
```

- [ ] **Step 2: Run to verify the new test fails**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: `test_bundle_includes_connection_json_when_provided` FAILS with
`TypeError: build_bundle_zip() got an unexpected keyword argument
'connection'`. `test_bundle_omits_connection_json_by_default` passes already
(current behavior already omits the file — kept as an explicit regression
guard for this task, not a new failure).

- [ ] **Step 3: Update `bundler.py`**

Replace the full contents of `core/app/appexport/bundler.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Assemble le zip d'export : runtime prébâti (jamais reconstruit par ce
job) + config sérialisée en JSON, lue au runtime par
shell/src/staticExport/entry.tsx via un fetch relatif — aucune invocation
Node/Vite ici.

Mode Statique (SP-18a) : `connection=None`, le fichier geostudio-app-
config.json contient la config déjà gelée (freeze_config) par l'appelant.
Mode Connecté (SP-18b) : `connection={"coreUrl": ...}`, la config passée
n'est PAS gelée (elle garde ses DataSources "features"/"statistics"
d'origine) — un second fichier geostudio-connection.json embarque l'URL du
cœur d'origine ; sa présence/absence dans le zip est le seul signal dont
entry.tsx a besoin pour choisir createItemClient (réseau réel) vs
createStaticItemClient (aucun réseau)."""
import io
import json
import os
import zipfile

from app.configs.schemas import BuilderConfig


def build_bundle_zip(
    config: BuilderConfig, *, runtime_dir: str, connection: dict | None = None,
) -> bytes:
    entry_path = os.path.join(runtime_dir, "index.export.html")
    if not os.path.isfile(entry_path):
        raise FileNotFoundError(f"export runtime not found at {entry_path}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with open(entry_path, "rb") as f:
            zf.writestr("index.html", f.read())
        assets_dir = os.path.join(runtime_dir, "assets")
        if os.path.isdir(assets_dir):
            for name in os.listdir(assets_dir):
                with open(os.path.join(assets_dir, name), "rb") as f:
                    zf.writestr(f"assets/{name}", f.read())
        zf.writestr("geostudio-app-config.json", config.model_dump_json(by_alias=True))
        if connection is not None:
            zf.writestr("geostudio-connection.json", json.dumps(connection))
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/bundler.py core/tests/test_appexport_bundler.py
git commit -m "feat(core): bundler embeds an optional geostudio-connection.json (SP-18b)"
```

---

