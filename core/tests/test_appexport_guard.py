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
        LayoutItem(id=f"w{i}", widget=t, x=0, y=i, w=4, h=2) for i, t in enumerate(widget_types)
    ]
    return BuilderConfig(
        kind="app",
        dataSources=data_sources,
        layout=Layout(type="grid", items=[]),
        pages=[Page(id="p1", name="Page 1", layout=Layout(type="grid", items=items))],
    )


def _public_collection(s):
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
    col = create_collection(
        s,
        tenant_id=tenant.id,
        owner_id=owner.id,
        table_name="t_x",
        title="X",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type="point",
        srid=4326,
    )
    s.commit()
    return tenant.id, col


def _private_collection(s):
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
    col = create_collection(
        s,
        tenant_id=tenant.id,
        owner_id=owner.id,
        table_name="t_x",
        title="X",
        description="",
        is_public=False,
        pk_column="id",
        geometry_column=None,
        geometry_type="point",
        srid=4326,
    )
    s.commit()
    return tenant.id, col


def test_no_data_sources_and_only_builtin_widgets_is_allowed():
    Session = _session()
    with Session() as s:
        result = check_export_guard(
            s, tenant_id="t1", config=_app_config(data_sources=[]), mode="static"
        )
    assert result.allowed is True
    assert result.reasons == []


def test_static_source_needs_no_check():
    Session = _session()
    with Session() as s:
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="static", service="core", layer="", query={"records": []}),
            ]
        )
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is True


def test_features_source_on_non_public_collection_is_blocked():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
            ]
        )
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="static")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_public_collection_is_allowed():
    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
            ]
        )
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="static")
    assert result.allowed is True


def test_features_source_on_missing_collection_is_blocked():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="features", service="core", layer="ghost", query={}),
            ]
        )
        result = check_export_guard(s, tenant_id=tenant.id, config=config, mode="static")
    assert result.allowed is False
    assert any("introuvable" in r for r in result.reasons)


def test_statistics_source_is_blocked_in_static_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="statistics", service="core", layer="x", query={}),
            ]
        )
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
            layout=Layout(
                type="grid",
                items=[
                    LayoutItem(id="w0", widget="acme-widget", x=0, y=0, w=4, h=2),
                ],
            ),
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
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
            ]
        )
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="connected")
    assert result.allowed is True


def test_statistics_source_on_non_public_collection_is_blocked_in_connected_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
            ]
        )
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="connected")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_non_public_collection_is_still_blocked_in_connected_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
            ]
        )
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
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
            ]
        )
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is True


def test_statistics_source_on_non_public_collection_is_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
            ]
        )
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_non_public_collection_is_still_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(
            data_sources=[
                DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
            ]
        )
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


def test_non_app_kind_is_blocked():
    # j10b-007 : la tâche refuse aussi un kind non exportable (garde = dernier rempart).
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[]).model_copy(update={"kind": "site"})
        result = check_export_guard(s, tenant_id="t1", config=config, mode="static")
    assert result.allowed is False
    assert any("site" in r for r in result.reasons)


# --- P11.04/05 (j10b-003, j10b-004) ---


def test_allowlist_matches_shell_builtin_widget_registry():
    import re
    from pathlib import Path

    from app.appexport.guard import _SUPPORTED_WIDGET_TYPES

    widgets_dir = Path(__file__).resolve().parents[2] / "shell/src/builder/widgets"
    registered: set[str] = set()
    for f in widgets_dir.glob("*.tsx"):
        if f.name.endswith(".test.tsx"):
            continue
        registered |= set(re.findall(r'registerWidget\(\{\s*type:\s*"([^"]+)"', f.read_text()))
    assert registered, "aucun widget lu — chemin du registre shell périmé"
    # REV-102 : addressSearch appelle GET /v1/geocode du cœur, absent d'un export
    # statique/autoporté — exclusion volontaire de l'allowlist.
    assert "addressSearch" in registered and "addressSearch" not in _SUPPORTED_WIDGET_TYPES
    assert registered - {"addressSearch"} == _SUPPORTED_WIDGET_TYPES


def _nested_config(widget: str, props: dict) -> BuilderConfig:
    return BuilderConfig(
        kind="app",
        dataSources=[],
        layout=Layout(type="grid", items=[]),
        pages=[
            Page(
                id="p1",
                name="P1",
                layout=Layout(
                    type="grid",
                    items=[LayoutItem(id="w", widget=widget, x=0, y=0, w=4, h=2, props=props)],
                ),
            )
        ],
    )


def test_third_party_widget_nested_in_container_is_blocked():
    inner = {"id": "i", "widget": "acme-gauge", "x": 0, "y": 0, "w": 2, "h": 2, "props": {}}
    cases = {
        "tabs": {"tabs": [{"id": "t", "label": "T", "items": [inner]}]},
        "modal": {"title": "M", "items": [inner]},
        "drawer": {"items": [inner]},
    }
    Session = _session()
    with Session() as s:
        for widget, props in cases.items():
            for mode in ("static", "standalone"):
                result = check_export_guard(
                    s, tenant_id="t1", config=_nested_config(widget, props), mode=mode
                )
                assert result.allowed is False, (widget, mode)
                assert any("acme-gauge" in r for r in result.reasons)
