# SPDX-License-Identifier: Apache-2.0
"""AUD-118 : le seed de démo crée aussi une carte, une app et un dashboard (une seule fois)."""

from sqlalchemy import text

from scripts.seed_demo import seed, seed_objects

from .test_seed_demo import pg_core, pytestmark  # noqa: F401  (fixture + marqueur postgis)


def test_seed_objects_creates_map_app_dashboard_once(pg_core):  # noqa: F811
    with pg_core() as session:
        seed(session)
        first = seed_objects(session)
        session.commit()
    assert first == ["Carte des incidents", "Suivi des incidents", "Tableau de bord (modèle)"]
    with pg_core() as session:
        kinds = dict(session.execute(text("SELECT title, resource_type FROM items")).all())
        assert kinds == {
            "Carte des incidents": "map",
            "Suivi des incidents": "app",
            "Tableau de bord (modèle)": "dashboard",
        }
        assert seed_objects(session) == []  # idempotent
