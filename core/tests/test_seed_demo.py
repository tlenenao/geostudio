import pytest
from sqlalchemy import text

from app.db import Base
from scripts.seed_demo import seed

pytestmark = pytest.mark.postgis

_CORE_TABLES_IN_FK_ORDER = (
    "collection_shares", "collections", "audit_log", "users", "tenants",
)


@pytest.fixture()
def pg_core(pg_engine, pg_session_factory, monkeypatch):
    # Base jetable : tables du cœur + tables de démo, nettoyées après.
    #
    # Adaptation vs. le brief : la DB de test partage son schéma avec les
    # autres tests postgis (alembic upgrade head déjà joué, alembic_version
    # au HEAD). drop_all() désynchroniserait alembic_version et casserait les
    # autres tests. On garde donc create_all() (idempotent, checkfirst) mais
    # on remplace le drop_all() en teardown par un TRUNCATE CASCADE ciblé des
    # lignes créées par seed() — le schéma du cœur reste en place. Les tables
    # de démo (incidents, points_interet), elles, sont bien DROP comme dans
    # le brief : elles n'existent pas en dehors de ce test.
    #
    # Deuxième adaptation : la DB de test est vide (aucun tenant/user), donc
    # seed()'s _owner() n'a ni admin existant ni --owner à utiliser — il lève
    # SystemExit sans CORE_ADMIN_SUBS. Le brief teste `seed(session)` sans
    # argument ; on reproduit fidèlement l'usage réel (démo lancée via env,
    # cf. docstring du script) en fixant CORE_ADMIN_SUBS pour la durée du
    # test, ce qui exerce le même chemin de bootstrap qu'un déploiement de
    # démo. monkeypatch défait la variable automatiquement en fin de test.
    monkeypatch.setenv("CORE_ADMIN_SUBS", "demo-admin-seed-test")
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS incidents (id serial PRIMARY KEY, "
            "titre text NOT NULL, geom geometry(Point, 4326))"))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS points_interet (id serial PRIMARY KEY, "
            "nom text NOT NULL, geom geometry(Point, 4326))"))
        # Table propre au démarrage : l'idempotence du test repose sur l'état
        # du registre, pas sur des lignes laissées par une exécution précédente.
        conn.execute(text("DELETE FROM collections"))
    yield pg_session_factory
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS incidents, points_interet CASCADE"))
        conn.execute(text(
            "TRUNCATE TABLE " + ", ".join(_CORE_TABLES_IN_FK_ORDER) + " CASCADE"))


def test_seed_registers_demo_collections(pg_core):
    with pg_core() as session:
        created = seed(session)
        session.commit()
    assert set(created) == {"incidents", "points_interet"}
    with pg_core() as session:
        rows = session.execute(text(
            "SELECT id, is_public, editable, feature_count FROM collections ORDER BY id")).all()
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [
        ("incidents", True, True, 0), ("points_interet", True, True, 0)]


def test_seed_is_idempotent(pg_core):
    with pg_core() as session:
        seed(session)
        session.commit()
    with pg_core() as session:
        assert seed(session) == []  # déjà enregistrées : rien à faire


def test_seed_writes_audit(pg_core):
    with pg_core() as session:
        seed(session)
        session.commit()
    with pg_core() as session:
        rows = session.execute(text(
            "SELECT action, actor_kind FROM audit_log")).all()
    assert ("collection.create", "system") in [(r[0], r[1]) for r in rows]
