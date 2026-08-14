# SPDX-License-Identifier: Apache-2.0
import io
import zipfile

from app.appexport.bundler import build_bundle_zip
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
