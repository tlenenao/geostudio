# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.extensions.models import Extension
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_extension_round_trips_json_columns():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
        ext = Extension(
            id="acme.gauge", tenant_id=tenant.id, owner_id=admin.id,
            tag="gauge-extension-widget", label="Jauge (extension)",
            module_url="https://example.com/gauge.js",
            props=[{"name": "initial", "type": "number", "label": "Valeur initiale", "default": 0}],
            events=["changed"], actions=["reset"],
            default_size={"w": 2, "h": 2},
            permissions={"collections": "all"},
        )
        s.add(ext)
        s.commit()

    with Session() as s:
        fetched = s.get(Extension, ("acme.gauge", tenant.id))
        assert fetched is not None
        assert fetched.props == [{"name": "initial", "type": "number", "label": "Valeur initiale", "default": 0}]
        assert fetched.events == ["changed"]
        assert fetched.default_size == {"w": 2, "h": 2}
        assert fetched.permissions == {"collections": "all"}
        assert fetched.enabled is True
