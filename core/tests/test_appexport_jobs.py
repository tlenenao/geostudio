# SPDX-License-Identifier: Apache-2.0
from app.appexport import repository as appexport_repo
from app.appexport.jobs import build_app_export_task
from app.collections.repository import create_collection
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import init_db, make_engine, make_session_factory
from app.items.repository import create_item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _setup(monkeypatch, tmp_path, *, with_private_source=False):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.export.html").write_text("<html></html>")
    monkeypatch.setenv("APPEXPORT_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio.test")
    monkeypatch.setenv("S3_ACCESS_KEY", "k")
    monkeypatch.setenv("S3_SECRET_KEY", "s")

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        data_sources = []
        if with_private_source:
            col = create_collection(
                s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_priv",
                title="Priv", description="", is_public=False,
                pk_column="id", geometry_column="geom",
                geometry_type="point", srid=4326,
            )
            data_sources = [DataSource(id="s1", type="features", service="core", layer=col.id, query={})]
        item = create_item(s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="App")
        config = BuilderConfig(
            kind="app", dataSources=data_sources,
            layout=Layout(type="grid", items=[]),
            pages=[Page(id="p1", name="P1", layout=Layout(
                type="grid", items=[LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2)],
            ))],
        )
        configs_repo.create_config(s, config, item.id, tenant_id=tenant.id)
        job = appexport_repo.create_job(s, tenant_id=tenant.id, item_id=item.id, user_id=owner.id, mode="static")
        s.commit()
    return Session, tenant.id, job.id


def _fake_s3():
    class _Fake:
        def create_bucket(self, Bucket):  # noqa: N803
            pass

        def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
            pass

        def put_object(self, **kwargs):
            pass

    return _Fake()


def test_job_disabled_flag_marks_error(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "false")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "error"
    assert "disabled" in job.error


def test_job_succeeds_and_marks_done(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "done"
    assert job.result_key == f"appexports/{job_id}.zip"


def test_job_guard_rejection_marks_error(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path, with_private_source=True)
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "error"
    assert "publique" in job.error
