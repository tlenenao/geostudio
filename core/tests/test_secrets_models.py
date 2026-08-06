# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError

from app.db import init_db, make_engine, make_session_factory
from app.secrets.models import ConnectorSecret
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_connector_secrets_table_is_registered():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    assert sa_inspect(engine).has_table("connector_secrets")


def test_connector_secret_row_round_trip():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
        secret = ConnectorSecret(
            id="sec1", tenant_id=tenant.id, name="my-api", kind="bearer_token",
            ciphertext=b"cipher", nonce=b"nonce123456", created_by=user.id,
        )
        s.add(secret)
        s.commit()
        fetched = s.get(ConnectorSecret, "sec1")
        assert fetched.name == "my-api"
        assert fetched.kind == "bearer_token"
        assert fetched.created_at is not None
        assert fetched.updated_at is not None


def test_connector_secret_unique_name_per_tenant():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
        s.add(ConnectorSecret(
            id="sec1", tenant_id=tenant.id, name="dup", kind="bearer_token",
            ciphertext=b"c1", nonce=b"n1", created_by=user.id,
        ))
        s.commit()
        s.add(ConnectorSecret(
            id="sec2", tenant_id=tenant.id, name="dup", kind="bearer_token",
            ciphertext=b"c2", nonce=b"n2", created_by=user.id,
        ))
        with pytest.raises(IntegrityError):
            s.commit()
