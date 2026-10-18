# SPDX-License-Identifier: Apache-2.0
"""AUD-118 : le seed de démo crée aussi une carte, une app et un dashboard (une seule fois) ;
reliquat L12 : un dataset, une alerte inactive et, ETL actif, un pipeline."""

from sqlalchemy import text

from scripts.seed_demo import seed, seed_objects

from .test_seed_demo import pg_core, pytestmark  # noqa: F401  (fixture + marqueur postgis)

BASE = {
    "Carte des incidents": "map",
    "Suivi des incidents": "app",
    "Tableau de bord (modèle)": "dashboard",
    "Incidents (jeu de données)": "dataset",
    "Alerte : incidents nombreux (inactive)": "alert",
}


def test_seed_objects_creates_demo_objects_once(pg_core, monkeypatch):  # noqa: F811
    monkeypatch.delenv("CORE_ETL_ENABLED", raising=False)
    with pg_core() as session:
        seed(session)
        first = seed_objects(session)
        session.commit()
    assert sorted(first) == sorted(BASE)
    with pg_core() as session:
        kinds = dict(session.execute(text("SELECT title, resource_type FROM items")).all())
        assert kinds == BASE
        assert seed_objects(session) == []  # idempotent


def test_seed_objects_adds_a_pipeline_when_etl_is_enabled(pg_core, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    with pg_core() as session:
        seed(session)
        first = seed_objects(session)
        session.commit()
    assert "Export des incidents (pipeline)" in first
    with pg_core() as session:
        assert seed_objects(session) == []
