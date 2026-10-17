# SPDX-License-Identifier: Apache-2.0
"""Génération d'AppConfig pour l'outil MCP create_form_app (SP-7) — mêmes
briques que le gabarit builder « Application de saisie » (SP-4c,
shell/src/builder/templates.ts), assemblées côté serveur à partir du schéma
introspecté d'une collection plutôt que choisies à la main dans le builder."""

from app.collections import repository as collections_repo
from app.collections.models import Collection
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Message
from app.sharing.authorization import can
from app.users.models import User


def can_write_collection(session, *, user: User, col: Collection) -> bool:
    """Mirror of app/collections/routes.py's _can_write_collection (private
    to that module, no user=None branch needed here — an MCP tool always has
    a resolved user via _resolve_actor)."""
    return col.editable and can(
        session,
        user_id=user.id,
        action="write",
        item=collections_repo.get_access_facts(col),
        kind="collection",
        actor_is_admin=user.acts_as_admin(),
    )


def form_fields_from_schema(schema: dict) -> list[dict]:
    """Python mirror of shell/src/builder/widgets/form.tsx's
    fieldsFromSchema: 1:1 mapping over schema["fields"], order=index,
    hidden=False always, required carried over, maxLength/values passed
    through when present. Kept in sync by the structural tests in
    tests/test_mcp_form_app.py rather than shared code across the TS/Python
    boundary (same trade-off as CEL's cel-js/cel-python, arbitrage A8)."""
    fields = []
    for i, f in enumerate(schema["fields"]):
        entry: dict = {
            "name": f["name"],
            "type": f["type"],
            "label": f["name"],
            "order": i,
            "hidden": False,
            "required": f["required"],
        }
        if "maxLength" in f:
            entry["maxLength"] = f["maxLength"]
        if "values" in f:
            entry["values"] = f["values"]
        fields.append(entry)
    return fields


def build_config(*, collection_id: str, schema: dict, include_form: bool) -> BuilderConfig:
    data_source_id = f"{collection_id}-ds"
    data_sources = [
        DataSource(
            id=data_source_id, type="features", service="core", layer=collection_id, query={}
        )
    ]
    columns = [f["name"] for f in schema["fields"]]

    items: list[LayoutItem] = []
    messages: list[Message] = []
    if include_form:
        items.append(
            LayoutItem(
                id="form",
                widget="form",
                x=0,
                y=0,
                w=4,
                h=6,
                props={
                    "dataSourceId": data_source_id,
                    "fields": form_fields_from_schema(schema),
                    "submitLabel": "Enregistrer",
                    "geometryType": schema["geometry"]["type"] if schema["geometry"] else None,
                },
            )
        )
        items.append(
            LayoutItem(
                id="map",
                widget="map",
                x=4,
                y=0,
                w=8,
                h=4,
                props={"dataSourceId": data_source_id},
            )
        )
        items.append(
            LayoutItem(
                id="table",
                widget="table",
                x=4,
                y=4,
                w=8,
                h=2,
                props={"dataSourceId": data_source_id, "columns": columns, "pageSize": 10},
            )
        )
        messages.append(
            Message(
                **{"from": "table", "event": "itemSelected", "to": "form", "action": "loadRecord"}
            )
        )
    else:
        items.append(
            LayoutItem(
                id="map",
                widget="map",
                x=0,
                y=0,
                w=8,
                h=4,
                props={"dataSourceId": data_source_id},
            )
        )
        items.append(
            LayoutItem(
                id="table",
                widget="table",
                x=0,
                y=4,
                w=8,
                h=2,
                props={"dataSourceId": data_source_id, "columns": columns, "pageSize": 10},
            )
        )

    return BuilderConfig(
        kind="app",
        dataSources=data_sources,
        layout=Layout(type="grid", breakpoints={}, items=items),
        messages=messages,
    )


def build_collect_config(
    *, collection_id: str, form_fields: list[dict], geometry_type: str | None
) -> BuilderConfig:
    """App de collecte terrain issue d'un XLSForm (ARC-27) : un seul widget formulaire
    mobile-first (GPS, photo, liste « mes saisies »), champs et `visibleWhen` tels qu'importés."""
    data_source_id = f"{collection_id}-ds"
    return BuilderConfig(
        kind="app",
        dataSources=[
            DataSource(
                id=data_source_id, type="features", service="core", layer=collection_id, query={}
            )
        ],
        layout=Layout(
            type="grid",
            breakpoints={},
            items=[
                LayoutItem(
                    id="form",
                    widget="form",
                    x=0,
                    y=0,
                    w=12,
                    h=10,
                    props={
                        "dataSourceId": data_source_id,
                        "fields": form_fields,
                        "submitLabel": "Envoyer",
                        "geometryType": geometry_type,
                        "mobile": True,
                        "showMyEntries": True,
                    },
                )
            ],
        ),
        messages=[],
    )
