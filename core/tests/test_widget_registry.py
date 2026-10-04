# SPDX-License-Identifier: Apache-2.0
"""REV-278a : un type de widget inconnu est refusé à l'écriture ; accepté s'il
est natif ou s'il correspond à une extension activée du tenant."""

import pytest
from fastapi import HTTPException

from app.configs.schemas import BuilderConfig
from app.configs.widget_registry import (
    BUILTIN_WIDGET_TYPES,
    validate_widget_types,
    widget_type_errors,
)
from app.db import init_db, make_engine, make_session_factory
from app.extensions.models import Extension
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _cfg(*widgets):
    items = [
        {"id": wid, "widget": wtype, "x": 0, "y": i, "w": 4, "h": 2, "props": props}
        for i, (wid, wtype, props) in enumerate(widgets)
    ]
    return BuilderConfig.model_validate({"kind": "app", "layout": {"type": "grid", "items": items}})


def _tenant_session(*, extension_enabled=True):
    s = _make_session()()
    tenant = get_or_create_default_tenant(s)
    user = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="u", username="u", email=None, first_name="", last_name=""
    )
    s.add(
        Extension(
            id="acme.gauge", tenant_id=tenant.id, owner_id=user.id, tag="acme-gauge",
            label="Jauge", module_url="https://cdn.example.com/g.js", props=[], events=None,
            actions=None, default_size={"w": 2, "h": 2}, permissions={}, enabled=extension_enabled,
        )
    )  # fmt: skip
    s.commit()
    return s, tenant.id


def test_builtin_set_is_non_trivial():
    assert {"map", "chart", "table", "form"} <= BUILTIN_WIDGET_TYPES


def test_builtin_widgets_are_accepted():
    s, tid = _tenant_session()
    assert widget_type_errors(s, _cfg(("a", "map", {}), ("b", "chart", {})), tenant_id=tid) == []


def test_registered_extension_is_accepted():
    s, tid = _tenant_session()
    assert widget_type_errors(s, _cfg(("g", "acme.gauge", {})), tenant_id=tid) == []


def test_disabled_extension_is_refused():
    s, tid = _tenant_session(extension_enabled=False)
    assert widget_type_errors(s, _cfg(("g", "acme.gauge", {})), tenant_id=tid)


def test_unknown_widget_type_is_refused_with_its_id():
    s, tid = _tenant_session()
    errors = widget_type_errors(s, _cfg(("zz", "hologram", {})), tenant_id=tid)
    assert errors == ["widget 'zz': unknown widget type 'hologram'"]
    with pytest.raises(HTTPException) as exc:
        validate_widget_types(s, _cfg(("zz", "hologram", {})), tenant_id=tid)
    assert exc.value.status_code == 422


def test_unknown_nested_widget_in_a_modal_is_refused():
    s, tid = _tenant_session()
    inner = {"id": "inner", "widget": "hologram", "x": 0, "y": 0, "w": 1, "h": 1}
    modal = ("m", "modal", {"items": [inner]})
    assert widget_type_errors(s, _cfg(modal), tenant_id=tid) == [
        "widget 'inner': unknown widget type 'hologram'"
    ]


def test_extension_of_another_tenant_is_refused():
    s, _tid = _tenant_session()
    assert widget_type_errors(s, _cfg(("g", "acme.gauge", {})), tenant_id="other-tenant")
