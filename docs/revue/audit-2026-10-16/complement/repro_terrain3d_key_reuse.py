"""Repro (lecture seule, SQLite en memoire) : POST /v1/terrain3d/uploads accepte comme "upload"
la cle d'un DEM converti existant. Lancer depuis core/ :
  PYTHONPATH=. uv run pytest ../docs/revue/audit-2026-10-16/complement/repro_terrain3d_key_reuse.py \
     -p no:cacheprovider --rootdir . -c pyproject.toml -q
"""
from tests.test_terrain3d_routes import env  # noqa: F401


def test_existing_converted_dem_key_is_accepted_as_upload(env):  # noqa: F811
    client, _Session, tenant, _alice, deferred, _s3 = env
    victim_key = f"{tenant.id}/0123456789abcdef0123456789abcdef/dem-cog.tif"  # sourceKey d'un item terrain3d existant
    r = client.post(
        "/v1/terrain3d/uploads",
        json={"key": victim_key, "filename": "x.tif", "title": "copie"},
    )
    print("terrain3d status:", r.status_code, r.text)
    assert r.status_code == 201  # aucune verification de forme ni d'usage : le job est differe
    assert deferred  # convert_terrain3d_task lira puis SUPPRIMERA victim_key (jobs.py:199)


def test_presign_filename_is_not_validated(env):  # noqa: F811
    client, *_ = env
    r = client.post("/v1/terrain3d/uploads/presign", json={"filename": "../../x/y.tif"})
    print("presign status:", r.status_code, r.text)
    assert r.status_code == 200 and "../../x/y.tif" in r.json()["key"]
