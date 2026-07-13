from app.db import init_db, make_engine, make_session_factory
from app.extensions import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _env():
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
    return Session, tenant.id, admin.id


def test_create_get_and_list_active():
    Session, tenant_id, owner_id = _env()
    with Session() as s:
        repo.create_extension(
            s, tenant_id=tenant_id, owner_id=owner_id, id="acme.gauge",
            tag="gauge-extension-widget", label="Jauge (extension)",
            module_url="https://example.com/gauge.js",
            props=[], events=["changed"], actions=["reset"],
            default_size={"w": 2, "h": 2}, permissions={"collections": "all"},
        )
        s.commit()

    with Session() as s:
        ext = repo.get_extension(s, tenant_id=tenant_id, extension_id="acme.gauge")
        assert ext is not None and ext.label == "Jauge (extension)"
        assert [e.id for e in repo.list_extensions(s, tenant_id=tenant_id)] == ["acme.gauge"]


def test_list_active_excludes_disabled():
    Session, tenant_id, owner_id = _env()
    with Session() as s:
        ext = repo.create_extension(
            s, tenant_id=tenant_id, owner_id=owner_id, id="acme.gauge",
            tag="gauge-extension-widget", label="Jauge", module_url="https://x/gauge.js",
            props=[], events=None, actions=None,
            default_size={"w": 2, "h": 2}, permissions={"collections": "all"},
        )
        repo.update_extension(s, ext, enabled=False)
        s.commit()

    with Session() as s:
        assert repo.list_extensions(s, tenant_id=tenant_id) == []
        # toujours récupérable par id, seule la liste "actives" l'exclut
        assert repo.get_extension(s, tenant_id=tenant_id, extension_id="acme.gauge") is not None


def test_list_extensions_include_disabled_returns_all():
    Session, tenant_id, owner_id = _env()
    with Session() as s:
        ext = repo.create_extension(
            s, tenant_id=tenant_id, owner_id=owner_id, id="acme.gauge",
            tag="gauge-extension-widget", label="Jauge", module_url="https://x/gauge.js",
            props=[], events=None, actions=None,
            default_size={"w": 2, "h": 2}, permissions={"collections": "all"},
        )
        repo.update_extension(s, ext, enabled=False)
        s.commit()

    with Session() as s:
        assert repo.list_extensions(s, tenant_id=tenant_id) == []
        assert [e.id for e in repo.list_extensions(s, tenant_id=tenant_id, include_disabled=True)] == ["acme.gauge"]
