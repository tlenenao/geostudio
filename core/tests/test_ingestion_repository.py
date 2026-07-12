from app.db import init_db, make_engine, make_session_factory
from app.ingestion import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _env():
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
    return Session, tenant, user


def test_create_and_get_job():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id
        assert job.status == "pending"
    with Session() as s:
        fetched = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched is not None
        assert fetched.filename == "f.geojson"
        assert fetched.collection_title == "Villes"


def test_get_job_scoped_to_tenant():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        assert repo.get_job(s, tenant_id="other-tenant", job_id=job_id) is None


def test_mark_running_then_done():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_running(s, job_id=job_id)
        s.commit()
    with Session() as s:
        repo.mark_done(s, job_id=job_id, collection_id="c1", item_id="i1")
        s.commit()
    with Session() as s:
        fetched = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "done"
        assert fetched.collection_id == "c1"
        assert fetched.item_id == "i1"


def test_mark_error():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_error(s, job_id=job_id, error_message="JSON invalide")
        s.commit()
    with Session() as s:
        fetched = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "error"
        assert fetched.error_message == "JSON invalide"


def test_create_job_stores_optional_lat_lon_fields():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.csv", collection_title="Villes",
            lat_field="y", lon_field="x",
        )
        s.commit()
        assert job.lat_field == "y"
        assert job.lon_field == "x"


def test_create_job_stores_layer_name():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="villes.gpkg", collection_title="Villes",
            lat_field=None, lon_field=None, layer_name="villes",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        fetched = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.layer_name == "villes"


def test_create_job_defaults_layer_name_to_none():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="villes.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        assert job.layer_name is None
