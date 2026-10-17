# SPDX-License-Identifier: Apache-2.0
from app.appexport.datasets import resolve_dataset_sources
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, DataSource, Layout
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _owner(s):
    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=False,
    )
    return tenant, owner


def _dataset(s, tenant, owner, payload: dict) -> str:
    item = items_repo.create_item(
        s, tenant_id=tenant.id, owner_id=owner.id, resource_type="dataset", title="D"
    )
    cfg = BuilderConfig.model_validate({"kind": "dataset", "dataset": payload})
    configs_repo.create_config(s, cfg, item.id, tenant_id=tenant.id)
    s.commit()
    return item.id


def _app(dataset_id: str) -> BuilderConfig:
    return BuilderConfig(
        kind="app",
        dataSources=[
            DataSource(
                id="s1", type="features", service="core", layer="", datasetId=dataset_id, query={}
            )
        ],
        layout=Layout(type="grid", items=[]),
    )


def test_collection_dataset_is_resolved_to_its_layer():
    with _env()() as s:
        tenant, owner = _owner(s)
        ds = _dataset(s, tenant, owner, {"source": "collection", "collectionId": "col-1"})
        cfg, reasons = resolve_dataset_sources(s, tenant_id=tenant.id, config=_app(ds))
    assert reasons == []
    assert cfg.dataSources[0].layer == "col-1"
    assert cfg.dataSources[0].datasetId is None


def test_arcgis_dataset_is_refused_with_explicit_reason():
    with _env()() as s:
        tenant, owner = _owner(s)
        ds = _dataset(s, tenant, owner, {"source": "arcgis", "arcgisItemId": "x"})
        _, reasons = resolve_dataset_sources(s, tenant_id=tenant.id, config=_app(ds))
    assert len(reasons) == 1 and "s1" in reasons[0] and "collection" in reasons[0]


def test_unknown_or_other_tenant_dataset_is_refused():
    with _env()() as s:
        tenant, _ = _owner(s)
        _, reasons = resolve_dataset_sources(s, tenant_id=tenant.id, config=_app("nope"))
    assert len(reasons) == 1 and "introuvable" in reasons[0]


def test_named_metric_measure_is_refused_with_explicit_reason():
    with _env()() as s:
        tenant, owner = _owner(s)
        ds = _dataset(s, tenant, owner, {"source": "collection", "collectionId": "col-1"})
        app = _app(ds)
        app.dataSources[0].type = "statistics"
        app.dataSources[0].query = {"measures": [{"metric": "total_pop"}]}
        _, reasons = resolve_dataset_sources(s, tenant_id=tenant.id, config=app)
    assert len(reasons) == 1 and "s1" in reasons[0] and "métriques nommées" in reasons[0]
