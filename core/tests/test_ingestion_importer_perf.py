"""Validation du critère M4 (feuille de route, §SP-6) : un GeoPackage de
50 000 entités s'importe en un temps trivial devant le budget UI de 5 min
(le budget UI couvre aussi le transfert réseau du fichier, hors périmètre
d'un test backend — cf. design SP-6b §11)."""
import time

import numpy as np
import pytest
import shapely
from pyogrio.raw import write as pyogrio_write
from shapely.geometry import Point
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.ingestion.importer import run_import
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

N_FEATURES = 50_000
# Seuil très en-dessous du budget M4 de 5 min (300s) : couvre une marge CI
# généreuse tout en restant un signal de régression utile. Mesuré en local
# (2026-07-12, hors CI) : lecture+reprojection pyogrio/pyproj de 50k points
# <0,1s, insertion PostGIS (executemany) <1s — le pipeline complet est de
# l'ordre de quelques secondes, très loin du seuil.
PERF_BUDGET_SECONDS = 180


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE items, configs, config_revisions, collections, "
            "audit_log, users, tenants CASCADE"
        ))


def _synthetic_gpkg_bytes(tmp_path) -> bytes:
    rng = np.random.default_rng(42)
    lons = rng.uniform(-5.0, 9.0, N_FEATURES)
    lats = rng.uniform(41.0, 51.0, N_FEATURES)
    geometry = shapely.to_wkb(
        np.array([Point(x, y) for x, y in zip(lons, lats)], dtype=object)
    )
    path = tmp_path / "big.gpkg"
    pyogrio_write(
        str(path), geometry=geometry,
        field_data=[
            np.array([f"entite-{i}" for i in range(N_FEATURES)], dtype=object),
            np.arange(N_FEATURES, dtype="int64"),
        ],
        fields=["nom", "rang"], layer="entites", geometry_type="Point", crs="EPSG:4326",
    )
    return path.read_bytes()


def test_gpkg_50k_features_imports_within_m4_budget(env, tmp_path):
    Session, tenant, user = env
    content = _synthetic_gpkg_bytes(tmp_path)

    with Session() as s:
        t0 = time.monotonic()
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="big.gpkg",
            content=content, collection_title="Gros import", lat_field=None,
            lon_field=None, layer_name="entites",
        )
        s.commit()
        elapsed = time.monotonic() - t0

    assert elapsed < PERF_BUDGET_SECONDS, (
        f"import de {N_FEATURES} entités trop lent : {elapsed:.1f}s "
        f"(budget {PERF_BUDGET_SECONDS}s)"
    )

    with Session() as s:
        count = s.execute(
            text(f"SELECT count(*) FROM public.{result.collection_id}")
        ).scalar_one()
        assert count == N_FEATURES
