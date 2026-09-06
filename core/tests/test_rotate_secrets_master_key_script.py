# SPDX-License-Identifier: Apache-2.0
"""CLI ponctuel de rotation de la clé maître (GAP-75, design SP-59 §3.1) —
patron `scripts/seed_demo.py` : `DATABASE_URL` en variable d'environnement,
jamais un argument CLI."""

import base64
import tempfile
from pathlib import Path

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.secrets import crypto
from app.secrets import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from scripts.rotate_secrets_master_key import main

OLD_KEY_B64 = base64.b64encode(bytes(range(0, 32))).decode()
NEW_KEY_B64 = base64.b64encode(bytes(range(31, 63))).decode()


@pytest.fixture()
def tmp_sqlite_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "rotation-test.sqlite3"
        database_url = f"sqlite+pysqlite:///{db_path}"
        engine = make_engine(database_url)
        init_db(engine)
        Session = make_session_factory(engine)
        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            user = get_or_create_user(
                session,
                tenant_id=tenant.id,
                oidc_sub="a",
                username="alice",
                email=None,
                first_name="",
                last_name="",
            )
            ciphertext, nonce = crypto.encrypt(
                {"kind": "bearer_token", "token": "s3cr3t"},
                key=base64.b64decode(OLD_KEY_B64),
            )
            repo.create_secret(
                session,
                tenant_id=tenant.id,
                created_by=user.id,
                name="my-secret",
                kind="bearer_token",
                ciphertext=ciphertext,
                nonce=nonce,
            )
            session.commit()
        engine.dispose()
        monkeypatch.setenv("DATABASE_URL", database_url)
        yield database_url


def test_dry_run_does_not_write(tmp_sqlite_db, monkeypatch, capsys):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", OLD_KEY_B64)
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY_NEW", NEW_KEY_B64)

    main(["--dry-run"])

    engine = make_engine(tmp_sqlite_db)
    Session = make_session_factory(engine)
    with Session() as session:
        (secret,) = repo.list_all_secrets(session)
        # le secret décrypte toujours avec l'ANCIENNE clé : --dry-run n'a
        # rien écrit.
        assert crypto.decrypt(
            secret.ciphertext, secret.nonce, key=base64.b64decode(OLD_KEY_B64)
        ) == {"kind": "bearer_token", "token": "s3cr3t"}
    engine.dispose()


def test_missing_new_key_exits_nonzero_without_touching_db(tmp_sqlite_db, monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", OLD_KEY_B64)
    monkeypatch.delenv("CORE_SECRETS_MASTER_KEY_NEW", raising=False)
    with pytest.raises(SystemExit):
        main([])

    engine = make_engine(tmp_sqlite_db)
    Session = make_session_factory(engine)
    with Session() as session:
        (secret,) = repo.list_all_secrets(session)
        assert crypto.decrypt(
            secret.ciphertext, secret.nonce, key=base64.b64decode(OLD_KEY_B64)
        ) == {"kind": "bearer_token", "token": "s3cr3t"}
    engine.dispose()


def test_real_run_commits_and_prints_operational_reminder(tmp_sqlite_db, monkeypatch, capsys):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", OLD_KEY_B64)
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY_NEW", NEW_KEY_B64)

    main([])

    out = capsys.readouterr().out
    assert "redémarrer" in out.lower() or "restart" in out.lower()

    engine = make_engine(tmp_sqlite_db)
    Session = make_session_factory(engine)
    with Session() as session:
        (secret,) = repo.list_all_secrets(session)
        assert crypto.decrypt(
            secret.ciphertext, secret.nonce, key=base64.b64decode(NEW_KEY_B64)
        ) == {"kind": "bearer_token", "token": "s3cr3t"}
    engine.dispose()
