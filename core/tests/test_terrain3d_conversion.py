# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.terrain3d.conversion import Terrain3DConversionError, convert_to_cog


def _write_test_geotiff(path: str, *, width: int = 1024, height: int = 1024) -> None:
    # 1024×1024 : cog_translate calcule le nombre d'overviews via
    # get_maximum_overview_level(width, height, minsize=blocksize) avec un
    # bloc par défaut de 512 — en dessous de ~768px la surimpression calculée
    # est 0 et le raster produit n'a alors aucune overview, ce qui n'est pas
    # un défaut de convert_to_cog mais le seuil réel de cette version de
    # rio-cogeo (vérifié directement contre rasterio.rio.overview).
    data = np.linspace(0, 1000, width * height, dtype="float32").reshape(height, width)
    # Origine non nulle avec pixel de 0.001° : (0, 0, 1, 1) produirait une
    # matrice affine égale à l'identité inversée, que GDAL refuse d'écrire
    # silencieusement (NotGeoreferencedWarning promu en erreur par
    # filterwarnings=["error"] dans ce dépôt) — sans lien avec le
    # comportement testé ici (conversion COG d'un raster valide).
    transform = from_origin(2.0, 45.0, 0.001, 0.001)
    with rasterio.open(
        path, "w", driver="GTiff", width=width, height=height, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)


def test_convert_to_cog_produces_a_valid_cog(tmp_path):
    src = tmp_path / "raw.tif"
    dst = tmp_path / "cog.tif"
    _write_test_geotiff(str(src))

    convert_to_cog(str(src), str(dst))

    assert dst.exists()
    with rasterio.open(str(dst)) as ds:
        assert ds.driver == "GTiff"
        assert ds.overviews(1) != []  # COG requires overviews
        assert ds.profile.get("tiled") is True


def test_convert_to_cog_rejects_a_non_raster_file(tmp_path):
    src = tmp_path / "raw.tif"
    src.write_bytes(b"not a geotiff at all")
    dst = tmp_path / "cog.tif"
    with pytest.raises(Terrain3DConversionError, match="lisible"):
        convert_to_cog(str(src), str(dst))


@pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")
def test_convert_to_cog_rejects_a_raster_without_a_crs(tmp_path):
    src = tmp_path / "raw.tif"
    dst = tmp_path / "cog.tif"
    data = np.zeros((8, 8), dtype="float32")
    with rasterio.open(
        src, "w", driver="GTiff", width=8, height=8, count=1, dtype="float32",
    ) as ds:  # no crs=, no transform=
        ds.write(data, 1)
    with pytest.raises(Terrain3DConversionError, match="CRS"):
        convert_to_cog(str(src), str(dst))


def test_convert_to_cog_raises_on_timeout(tmp_path, monkeypatch):
    # Le timeout s'appuie sur un process fils forké (jamais signal.alarm, qui
    # lève ValueError hors du thread principal — un worker procrastinate
    # n'exécute jamais ses tâches sync dans le thread principal). Le fork
    # hérite du monkeypatch ci-dessous ; le marqueur écrit *par le fils*
    # prouve que c'est bien la version lente qui a tourné (sans lui, un
    # cog_translate réel — ~0,3s sur ce raster — finirait avant le délai et
    # le test passerait pour la mauvaise raison).
    import time

    from app.terrain3d import conversion

    src = tmp_path / "raw.tif"
    dst = tmp_path / "cog.tif"
    marker = tmp_path / "child-ran"
    _write_test_geotiff(str(src))

    def _slow_cog_translate(*args, **kwargs):
        marker.write_text("stub")
        time.sleep(30)

    monkeypatch.setattr(conversion, "cog_translate", _slow_cog_translate)
    started = time.monotonic()
    with pytest.raises(Terrain3DConversionError, match="interrompue"):
        convert_to_cog(str(src), str(dst), timeout_seconds=1)
    elapsed = time.monotonic() - started

    assert marker.exists()  # le monkeypatch a bien été hérité par le fils
    assert elapsed < 20  # le fils a été tué, pas attendu jusqu'à ses 30s
    assert not dst.exists()  # aucun COG produit


def test_convert_to_cog_surfaces_a_child_process_failure(tmp_path, monkeypatch):
    # L'échec survient maintenant dans un autre process : sans le canal de
    # retour, il ressortirait en "processus interrompu" opaque (ou pire, en
    # succès silencieux).
    from app.terrain3d import conversion

    src = tmp_path / "raw.tif"
    dst = tmp_path / "cog.tif"
    _write_test_geotiff(str(src))

    def _boom(*args, **kwargs):
        raise RuntimeError("GDAL a explosé")

    monkeypatch.setattr(conversion, "cog_translate", _boom)
    with pytest.raises(Terrain3DConversionError, match="GDAL a explosé"):
        convert_to_cog(str(src), str(dst), timeout_seconds=30)
