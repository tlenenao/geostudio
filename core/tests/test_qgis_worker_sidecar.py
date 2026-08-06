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
