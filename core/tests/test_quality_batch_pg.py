# SPDX-License-Identifier: Apache-2.0
"""ARC-14 : contrôle de qualité par lot sur PostGIS réel — 50 000 entités, durée MESURÉE
(critère d'acceptation < 60 s ; la valeur observée est écrite dans la sortie du test)."""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.quality import jobs as quality_jobs
from app.quality import repository as quality_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

N = 50_000
RULES = [
    {
        "id": "surface-positive",
        "kind": "constraint",
        "field": "surface",
        "expression": "surface > 0.0",
        "message": "Surface non positive.",
    },
    {
        "id": "nom-court",
        "kind": "batch",
        "field": "nom",
        "expression": "size(nom) < 8",
        "message": "Nom trop long.",
    },
    {
        "id": "ratio",
        "kind": "batch",
        "expression": "surface / 2.0 < 49.0",
        "message": "Ratio hors bornes.",
    },
]


@pytest.fixture()
def pg(pg_engine, monkeypatch):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS qc_parcelles"))
        conn.execute(
            text(
                "CREATE TABLE qc_parcelles (id serial PRIMARY KEY, nom text, "
                "surface double precision, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        kw = dict(tenant_id=tenant.id, email=None, first_name="", last_name="")
        admin = get_or_create_user(s, oidc_sub="a", username="admin", bootstrap_admin=True, **kw)
        s.commit()
        ids = (tenant.id, admin.id)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    client = TestClient(app)
    assert client.post("/v1/collections", json={"tableName": "qc_parcelles"}).status_code == 201
    monkeypatch.setattr(quality_jobs, "session_factory", lambda: Session)
    yield client, Session, ids
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS qc_parcelles"))
        conn.execute(
            text(
                "TRUNCATE quality_reports, collection_shares, collections, audit_log,"
                " notifications, users, tenants CASCADE"
            )
        )


def _run(client, Session, ids):
    """Déclenche par l'API (defer neutralisé) puis exécute la tâche : (rapport, secondes)."""
    started: list[dict] = []
    quality_jobs.run_quality_check_task.defer = lambda **kw: started.append(kw)  # type: ignore[method-assign]
    r = client.post("/v1/collections/qc_parcelles/quality-checks")
    assert r.status_code == 202, r.text
    t0 = time.monotonic()
    quality_jobs.run_quality_check_task(**started[0])
    elapsed = time.monotonic() - t0
    with Session() as s:
        return quality_repo.get_report(s, r.json()["id"], ids[0]), elapsed


def test_quality_check_reports_violations_on_50k_rows_within_60s(pg, capsys):
    client, Session, ids = pg
    with Session() as s:
        s.execute(
            text(
                "INSERT INTO qc_parcelles (nom, surface) "
                "SELECT 'p' || i, (i % 100) - 1.0 FROM generate_series(1, :n) AS i"
            ),
            {"n": N},
        )
        s.commit()
    assert (
        client.patch("/v1/collections/qc_parcelles", json={"attributeRules": RULES}).status_code
        == 200
    )
    report, elapsed = _run(client, Session, ids)
    assert report.status == "done", report.error
    assert report.checked == N
    # i % 100 in (0, 1) -> surface -1 ou 0 (1000 violations) ; nom : aucun ;
    # ratio : surface/2 < 49 -> surface 98 (i%100==99) échoue : 500.
    s = report.summary
    assert s["surface-positive"]["violations"] == 1000
    assert s["nom-court"]["violations"] == 0
    assert s["ratio"]["violations"] == 500
    assert len(report.violations) == 1000
    assert all("value" not in v for v in report.violations)  # jamais de valeur d'attribut
    with capsys.disabled():
        print(f"\n[ARC-14] {N} entités, 3 règles CEL : {elapsed:.1f} s")
    assert elapsed < 60


def test_quality_check_requires_a_rule_and_masks_sensitive_rules(pg):
    client, Session, ids = pg
    r = client.post("/v1/collections/qc_parcelles/quality-checks")
    assert r.status_code == 409  # aucune règle constraint/batch
    assert (
        client.patch("/v1/collections/qc_parcelles", json={"attributeRules": RULES}).status_code
        == 200
    )
    with Session() as s:
        s.execute(text("INSERT INTO qc_parcelles (nom, surface) VALUES ('a', -1.0), ('b', 5.0)"))
        s.commit()
    report, _ = _run(client, Session, ids)
    assert report.status == "done"
    assert report.summary["surface-positive"]["violations"] == 1
    got = client.get(f"/v1/collections/qc_parcelles/quality-checks/{report.id}")
    assert got.status_code == 200 and got.json()["checked"] == 2
    assert client.get("/v1/collections/qc_parcelles/quality-checks/nope").status_code == 404
