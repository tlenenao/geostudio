from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import DEFAULT_TENANT_SLUG, get_or_create_default_tenant


def test_default_tenant_id_is_the_readable_slug():
    # Décision 2026-07-10 (spec SP-3, notes de revue SP-3a) : tenants.id est un
    # identifiant lisible immuable, aligné sur le seed de la migration 0002
    # (id='default'). C'est cette valeur que la RLS compare
    # (SET LOCAL app.tenant_id = user.tenant_id) et que le DDL stampe dans les
    # données métier — le chemin code et le chemin migration doivent produire
    # le même id.
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        assert tenant.id == DEFAULT_TENANT_SLUG
        assert get_or_create_default_tenant(session).id == tenant.id
