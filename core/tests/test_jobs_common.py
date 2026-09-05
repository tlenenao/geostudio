# SPDX-License-Identifier: Apache-2.0
"""Module de support de job partagé — SP-43 Étape 5 (Tâche 6). Remplace
`_session_factory()`/`_owner_user()`/`_acting_user()`/`_notify()` dupliqués
sur 5-6 fichiers de job procrastinate. `notify_best_effort()` préserve
l'invariant déjà correct sur les 5-6 sites actuels (le try/except de
notification est strictement séparé du commit de statut du job, cf. SP-39
UnboundLocalError x2 sur app.ingestion.tasks/app.pipelines.jobs) : un échec
dans notify_best_effort ne doit JAMAIS remonter à l'appelant.

Pas de fixtures `db_session`/`tenant`/`user` dans tests/conftest.py (vérifié :
ce fichier ne définit que des fixtures scope="session" pour DCAT/SHACL) —
setup local, même patron que tests/test_export_jobs.py::db_session (moteur
SQLite fichier + DATABASE_URL en env, pour que `session_factory()` ouvre une
connexion distincte vers la même base)."""

from unittest.mock import patch

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.items.repository import create_item
from app.jobs.common import notify_best_effort, resolve_owner_user, session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    db_path = tmp_path / "jobs_common.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="Alice",
        last_name="",
        bootstrap_admin=False,
    )
    item = create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="Carte test"
    )
    session.commit()
    try:
        yield session, tenant, user, item
    finally:
        session.close()


def test_session_factory_returns_a_working_session_factory(monkeypatch, tmp_path):
    db_path = tmp_path / "session_factory.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    factory = session_factory()
    session = factory()
    try:
        assert session is not None
    finally:
        session.close()


def test_session_factory_falls_back_to_in_memory_sqlite_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    factory = session_factory()
    session = factory()
    try:
        assert session is not None
    finally:
        session.close()


def test_resolve_owner_user_returns_the_item_owner(db_session):
    session, tenant, user, item = db_session
    owner = resolve_owner_user(session, tenant_id=tenant.id, item_id=item.id)
    assert owner.id == user.id


def test_resolve_owner_user_raises_lookup_error_when_item_not_found(db_session):
    session, tenant, _user, _item = db_session
    with pytest.raises(LookupError):
        resolve_owner_user(session, tenant_id=tenant.id, item_id="does-not-exist")


def test_notify_best_effort_writes_a_notification(db_session):
    session, tenant, user, item = db_session
    notify_best_effort(
        lambda: session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        kind="report",
        status="done",
        item_id=item.id,
        item_resource_type="report",
        item_title=item.title,
    )
    from app.notifications.models import Notification

    rows = session.query(Notification).all()
    assert len(rows) == 1
    assert rows[0].recipient_user_id == user.id
    assert rows[0].kind == "report"
    assert rows[0].status == "done"


def test_notify_best_effort_failure_never_raises(db_session):
    """Falsification de l'isolation try/except — reproduit le mécanisme
    exact des 2 UnboundLocalError trouvés par SP-39 (ingestion/tasks.py,
    pipelines/jobs.py) : une exception dans le chemin de notification ne
    doit jamais empêcher l'appelant de continuer."""
    session, tenant, user, item = db_session
    with patch(
        "app.notifications.repository.create_notification",
        side_effect=RuntimeError("simulated notification backend failure"),
    ):
        # ne doit lever aucune exception
        notify_best_effort(
            lambda: session,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="report",
            status="done",
            item_id=item.id,
            item_resource_type="report",
            item_title=item.title,
        )
