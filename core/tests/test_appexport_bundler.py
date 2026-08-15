# SPDX-License-Identifier: Apache-2.0
import io
import zipfile

from app.appexport.bundler import build_bundle_zip, build_standalone_bundle_zip
from app.configs.schemas import BuilderConfig, Layout, LayoutItem, Page


def _config() -> BuilderConfig:
    return BuilderConfig(
        kind="app", dataSources=[],
        layout=Layout(type="grid", items=[]),
        pages=[Page(id="p1", name="Page 1", layout=Layout(
            type="grid", items=[LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2)],
        ))],
    )


def test_bundle_contains_runtime_assets_and_frozen_config(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.export.html").write_text("<html><body>runtime</body></html>")
    assets_dir = runtime_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "export-abc123.js").write_text("console.log('runtime js')")

    zip_bytes = build_bundle_zip(_config(), runtime_dir=str(runtime_dir))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "index.html" in names  # index.export.html renamed at zip root
        assert "assets/export-abc123.js" in names
        assert "geostudio-app-config.json" in names
        payload = zf.read("geostudio-app-config.json").decode("utf-8")
        assert '"kind"' in payload and '"app"' in payload


def test_bundle_raises_clearly_when_runtime_dir_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        build_bundle_zip(_config(), runtime_dir=str(tmp_path / "does-not-exist"))


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


def test_standalone_bundle_raises_clearly_when_snapshot_dir_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        build_standalone_bundle_zip(_config(), snapshot_dir=str(tmp_path / "does-not-exist"))
