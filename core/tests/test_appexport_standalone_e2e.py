# SPDX-License-Identifier: Apache-2.0
"""Preuve en conditions réelles (pas assérée), SP-18c design §5 : construit
l'image du mini-serveur localement (jamais un docker pull — aucun tag n'a
jamais été publié sur ce dépôt, cf. plan §Global Constraints), démarre un
conteneur à froid (image + volume de données vierges), vérifie qu'il sert
l'app et l'instantané sans qu'aucun Postgres/Keycloak/MinIO n'apparaisse
dans son compose. @pytest.mark.postgis (write_snapshot a besoin d'une
collection réelle) ET @pytest.mark.docker (besoin d'un démon Docker) —
skippé si l'un des deux manque."""

import io
import shutil
import socket
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
import requests
from sqlalchemy import text

import app.main  # noqa: F401 — import-only, registers every model on

# Base.metadata before create_all() — même piège que test_appexport_freeze.py.
from app.appexport.bundler import build_standalone_bundle_zip
from app.appexport.snapshot import write_snapshot
from app.collections.ddl import apply_collection_ddl
from app.collections.introspection_pg import introspect_table
from app.collections.repository import create_collection
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import Base, make_session_factory
from app.features.repository import insert_feature
from app.features.rls import rls_scope
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = [pytest.mark.postgis, pytest.mark.docker]

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_TAG = "geostudio-appexport-standalone:e2e-test"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=True)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def standalone_image():
    if not _docker_available():
        pytest.skip("docker non disponible — test standalone E2E skippé")
    subprocess.run(
        ["docker", "build", "-f", "deploy/appexport-standalone/Dockerfile", "-t", IMAGE_TAG, "."],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        timeout=900,
    )
    return IMAGE_TAG


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_standalone_e2e"))
        conn.execute(
            text(
                "TRUNCATE collection_shares, collections, audit_log, items, users, tenants CASCADE"
            )
        )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_cold_started_container_serves_app_and_snapshot(pg_session, standalone_image, tmp_path):
    s = pg_session
    s.execute(
        text(
            "CREATE TABLE t_standalone_e2e "
            "(id serial PRIMARY KEY, tenant_id text NOT NULL, name text)"
        )
    )
    s.commit()
    apply_collection_ddl(s, "t_standalone_e2e")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s,
        tenant_id=tenant.id,
        owner_id=owner.id,
        table_name="t_standalone_e2e",
        title="X",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    s.commit()
    info = introspect_table(s, col.table_name)
    with rls_scope(s, tenant.id):
        insert_feature(s, info, properties={"name": "Alpha"}, geometry=None)
    s.commit()

    config = BuilderConfig(
        kind="app",
        dataSources=[DataSource(id="s1", type="features", service="core", layer=col.id, query={})],
        layout=Layout(type="grid", items=[]),
        pages=[
            Page(
                id="p1",
                name="P1",
                layout=Layout(
                    type="grid",
                    items=[
                        LayoutItem(
                            id="w1",
                            widget="table",
                            x=0,
                            y=0,
                            w=4,
                            h=2,
                            props={"dataSourceId": "s1"},
                        )
                    ],
                ),
            )
        ],
    )

    snapshot_src = tmp_path / "snapshot-src"
    snapshot_src.mkdir()
    write_snapshot(s, tenant_id=tenant.id, config=config, snapshot_dir=str(snapshot_src))
    zip_bytes = build_standalone_bundle_zip(config, snapshot_dir=str(snapshot_src))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        compose_text = zf.read("docker-compose.yml").decode("utf-8")
        for forbidden in ("postgis", "keycloak", "minio"):
            assert forbidden not in compose_text.lower()
        for name in zf.namelist():
            if name.startswith("data/"):
                target = tmp_path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
    data_dir = tmp_path / "data"

    port = _free_port()
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-p",
            f"{port}:8000",
            "-v",
            f"{data_dir}:/data:ro",
            standalone_image,
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    container_id = run.stdout.strip()
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                if requests.get(f"{base}/geostudio-app-config.json", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            pytest.fail("le mini-serveur autoporté n'a jamais répondu")

        config_resp = requests.get(f"{base}/geostudio-app-config.json", timeout=5)
        assert config_resp.status_code == 200
        assert config_resp.json()["kind"] == "app"

        items_resp = requests.get(f"{base}/collections/{col.id}/items", timeout=5)
        assert items_resp.status_code == 200
        names = [f["properties"]["name"] for f in items_resp.json()["features"]]
        assert names == ["Alpha"]

        agg_resp = requests.post(
            f"{base}/collections/{col.id}/aggregate", json={"agg": "count"}, timeout=5
        )
        assert agg_resp.status_code == 200
        assert agg_resp.json()["rows"][0]["value"] == 1

        index_resp = requests.get(f"{base}/", timeout=5)
        assert index_resp.status_code == 200
        assert "text/html" in index_resp.headers["content-type"]
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)
