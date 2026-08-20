# SPDX-License-Identifier: Apache-2.0
"""Génération d'AppConfig pour create_form_app (SP-7 Task 10) — pure, sans
DB. Sert aussi de test de non-régression structurel pour le mapping
schéma->champs, dupliqué côté TS dans
shell/src/builder/widgets/form.tsx::fieldsFromSchema (même risque de dérive
que CEL, arbitrage A8 — voir spec §Architecture MCP v1)."""

import pytest

from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.mcp.form_app import build_config, can_write_collection, form_fields_from_schema
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

SCHEMA = {
    "collection": "incidents",
    "pk": "id",
    "geometry": {"column": "geom", "type": "Point", "srid": 4326},
    "fields": [
        {"name": "titre", "type": "string", "required": True, "maxLength": 200},
        {"name": "gravite", "type": "enum", "required": False, "values": ["faible", "haute"]},
    ],
}


def test_form_fields_from_schema_maps_every_field_visible_and_unordered_by_default():
    fields = form_fields_from_schema(SCHEMA)
    assert fields == [
        {
            "name": "titre",
            "type": "string",
            "label": "titre",
            "order": 0,
            "hidden": False,
            "required": True,
            "maxLength": 200,
        },
        {
            "name": "gravite",
            "type": "enum",
            "label": "gravite",
            "order": 1,
            "hidden": False,
            "required": False,
            "values": ["faible", "haute"],
        },
    ]


def test_build_config_with_form_includes_form_map_table_and_message():
    config = build_config(collection_id="incidents", schema=SCHEMA, include_form=True)
    widget_types = [item.widget for item in config.layout.items]
    assert widget_types == ["form", "map", "table"]
    assert len(config.messages) == 1
    assert config.messages[0].event == "itemSelected"
    assert config.messages[0].action == "loadRecord"
    table_item = next(i for i in config.layout.items if i.widget == "table")
    assert table_item.props["columns"] == ["titre", "gravite"]


def test_build_config_without_form_has_only_map_and_table():
    config = build_config(collection_id="incidents", schema=SCHEMA, include_form=False)
    widget_types = [item.widget for item in config.layout.items]
    assert widget_types == ["map", "table"]
    assert config.messages == []


@pytest.fixture()
def env():
    # Mirrors test_collections_authorization.py's `env` fixture: SQLite is
    # enough here, can_write_collection only reads ORM rows + calls can()
    # (no PostGIS/DDL involved) — that's reserved for the end-to-end test
    # in test_mcp_tools_create_form_app.py, which exercises the real MCP
    # tool call through apply_collection_ddl.
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        other = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="x",
            username="other",
            email=None,
            first_name="",
            last_name="",
        )
        col = Collection(
            id="col-1",
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name="col_1",
            title="Col 1",
            pk_column="id",
            editable=True,
        )
        session.add(col)
        session.commit()
        yield session, owner, other, col


def test_can_write_collection_true_for_owner(env):
    session, owner, other, col = env
    assert can_write_collection(session, user=owner, col=col) is True


def test_can_write_collection_false_for_non_owner_without_share(env):
    # `other` has no CollectionShare/editor role on `col` — the exact
    # scenario the review finding flagged as untested: a caller who is
    # neither owner nor shared-in must not get a write-capable Formulaire.
    session, owner, other, col = env
    assert can_write_collection(session, user=other, col=col) is False
