### Task 7: `build_standalone_bundle_zip`

**Files:**
- Modify: `core/app/appexport/bundler.py`
- Modify: `core/tests/test_appexport_bundler.py`

**Interfaces:**
- Produces: `build_standalone_bundle_zip(config: BuilderConfig, *,
  snapshot_dir: str) -> bytes` — zips `config` as `data/geostudio-app-config.json`,
  every file under `snapshot_dir` (manifest.json + snapshot/...) as
  `data/...`, plus a generated `docker-compose.yml` and `README.md` at the
  zip root. Consumed by Task 8's job.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_appexport_bundler.py` (existing content stays as-is above this):

```python


def _write_snapshot_fixture(tmp_path):
    snapshot_src = tmp_path / "snapshot-src"
    parquet_dir = snapshot_src / "snapshot" / "tenant_id=t1" / "collection_id=col1" / "dt=snapshot"
    parquet_dir.mkdir(parents=True)
    (parquet_dir / "data.parquet").write_bytes(b"fake-parquet-bytes")
    (snapshot_src / "manifest.json").write_text('{"collections": []}')
    return snapshot_src


def test_standalone_bundle_contains_data_manifest_and_compose(tmp_path):
    snapshot_src = _write_snapshot_fixture(tmp_path)

    zip_bytes = build_standalone_bundle_zip(_config(), snapshot_dir=str(snapshot_src))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "data/geostudio-app-config.json" in names
        assert "data/manifest.json" in names
        assert "data/snapshot/tenant_id=t1/collection_id=col1/dt=snapshot/data.parquet" in names
        assert "docker-compose.yml" in names
        assert "README.md" in names

        config_payload = zf.read("data/geostudio-app-config.json").decode("utf-8")
        assert '"kind"' in config_payload and '"app"' in config_payload

        compose = zf.read("docker-compose.yml").decode("utf-8")
        assert "ghcr.io/tlenenao/geostudio-appexport-standalone:latest" in compose
        assert "./data:/data:ro" in compose


def test_standalone_bundle_with_empty_snapshot_dir(tmp_path):
    snapshot_src = tmp_path / "empty-snapshot"
    snapshot_src.mkdir()
    (snapshot_src / "manifest.json").write_text('{"collections": []}')

    zip_bytes = build_standalone_bundle_zip(_config(), snapshot_dir=str(snapshot_src))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "data/manifest.json" in names
        assert "data/geostudio-app-config.json" in names
```

Add the import at the top of the file:

```python
from app.appexport.bundler import build_bundle_zip, build_standalone_bundle_zip
```

(replacing the existing `from app.appexport.bundler import build_bundle_zip` line)

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_standalone_bundle_zip'`

- [ ] **Step 3: Add `build_standalone_bundle_zip` to `bundler.py`**

In `core/app/appexport/bundler.py`, append after `build_bundle_zip`:

```python


_STANDALONE_COMPOSE = """\
services:
  app:
    image: ghcr.io/tlenenao/geostudio-appexport-standalone:latest
    ports:
      - "8090:8000"
    volumes:
      - ./data:/data:ro
    restart: unless-stopped
"""

_STANDALONE_README = """\
# App GeoStudio exportée (mode Autoporté)

## Démarrer

    docker compose up -d

Puis ouvrir http://localhost:8090

## Contenu

- `data/geostudio-app-config.json` : configuration de l'app (figée à l'export).
- `data/manifest.json` : métadonnées des collections figées.
- `data/snapshot/` : instantané des données au format GeoParquet.

Le conteneur est strictement en lecture seule : aucune donnée n'est jamais
écrite. Un ré-export manuel depuis GeoStudio est nécessaire pour rafraîchir
l'instantané.
"""


def build_standalone_bundle_zip(config: BuilderConfig, *, snapshot_dir: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data/geostudio-app-config.json", config.model_dump_json(by_alias=True))
        for root, _dirs, files in os.walk(snapshot_dir):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, snapshot_dir)
                zf.write(full, arcname=f"data/{rel}")
        zf.writestr("docker-compose.yml", _STANDALONE_COMPOSE)
        zf.writestr("README.md", _STANDALONE_README)
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/bundler.py core/tests/test_appexport_bundler.py
git commit -m "feat(core): build_standalone_bundle_zip — data+compose bundle (SP-18c)"
```

---

