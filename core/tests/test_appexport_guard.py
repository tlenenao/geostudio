# SPDX-License-Identifier: Apache-2.0
from app.appexport.guard import check_export_guard
from app.collections.repository import create_collection
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _app_config(*, data_sources, widget_types=("text",)) -> BuilderConfig:
    items = [
        LayoutItem(id=f"w{i}", widget=t, x=0, y=i, w=4, h=2)
        for i, t in enumerate(widget_types)
    ]
    return BuilderConfig(
        kind="app", dataSources=data_sources,
        layout=Layout(type="grid", items=[]),
        pages=[Page(id="p1", name="Page 1", layout=Layout(type="grid", items=items))],
    )


def _public_collection(s):
    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_x",
        title="X", description="", is_public=True,
        pk_column="id", geometry_column=None, geometry_type="point", srid=4326,
    )
    s.commit()
    return tenant.id, col


def _private_collection(s):
    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_x",
        title="X", description="", is_public=False,
        pk_column="id", geometry_column=None, geometry_type="point", srid=4326,
    )
    s.commit()
    return tenant.id, col


def test_no_data_sources_and_only_builtin_widgets_is_allowed():
    Session = _session()
    with Session() as s:
        result = check_export_guard(s, tenant_id="t1", config=_app_config(data_sources=[]), mode="static")
    assert result.allowed is True
    assert result.reasons == []


def test_static_source_needs_no_check():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[
            DataSource(id="s1", type="static", service="core", layer="", query={"records": []}),
        ])
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is True


def test_features_source_on_non_public_collection_is_blocked():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="static")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_public_collection_is_allowed():
    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="static")
    assert result.allowed is True


def test_features_source_on_missing_collection_is_blocked():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer="ghost", query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant.id, config=config, mode="static")
    assert result.allowed is False
    assert any("introuvable" in r for r in result.reasons)


def test_statistics_source_is_blocked_in_static_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer="x", query={}),
        ])
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is False
    assert any("agrégat" in r for r in result.reasons)


def test_unsupported_widget_type_is_blocked_in_static_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "acme-widget"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is False
    assert any("acme-widget" in r for r in result.reasons)


def test_unsupported_widget_in_top_level_layout_is_blocked_in_static_mode():
    Session = _session()
    with Session() as s:
        config = BuilderConfig(
            kind="app",
            dataSources=[],
            layout=Layout(type="grid", items=[
                LayoutItem(id="w0", widget="acme-widget", x=0, y=0, w=4, h=2),
            ]),
            pages=[],
        )
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is False
    assert any("acme-widget" in r for r in result.reasons)


# --- Connecté (SP-18b) : mêmes cas, comportement différent sur deux axes ---


def test_statistics_source_on_public_collection_is_allowed_in_connected_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="connected")
    assert result.allowed is True


def test_statistics_source_on_non_public_collection_is_blocked_in_connected_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="connected")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_non_public_collection_is_still_blocked_in_connected_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="connected")
    assert result.allowed is False


def test_third_party_widget_is_allowed_in_connected_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "acme-widget"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="connected")
    assert result.allowed is True
    assert result.reasons == []


# --- Autoporté (SP-18c) : leniency d'is_public de "connected", allowlist de widgets de "static" ---


def test_statistics_source_on_public_collection_is_allowed_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is True


def test_statistics_source_on_non_public_collection_is_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_non_public_collection_is_still_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is False


def test_unsupported_widget_type_is_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "acme-widget"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="standalone")
    assert result.allowed is False
    assert any("acme-widget" in r for r in result.reasons)


def test_builtin_widgets_only_is_allowed_in_standalone_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "table", "map"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="standalone")
    assert result.allowed is True
