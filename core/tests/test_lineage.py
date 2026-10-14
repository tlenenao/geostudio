# SPDX-License-Identifier: Apache-2.0
"""ARC4-F15 : lineage et vue d'impact — graphe dérivé des configs, filtré par visibilité.
Base sqlite en mémoire (config insérées brutes : le parcours est sur le JSON stocké)."""

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.models import Collection
from app.configs.models import Config, ConfigRevision
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.lineage import service
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.sharing.models import ItemShare  # noqa: F401  (table enregistrée)
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role


@pytest.fixture()
def world():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        viewer = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="v",
            username="viewer",
            email=None,
            first_name="",
            last_name="",
        )
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=viewer.id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        s.commit()
        ctx = {"Session": Session, "tenant": tenant.id, "owner": owner.id, "viewer": viewer.id}
    yield ctx
    engine.dispose()


def _add_item(s, ctx, kind, title, config, *, public=False, owner_key="owner") -> str:
    item_id = uuid.uuid4().hex
    s.add(
        Item(
            id=item_id,
            tenant_id=ctx["tenant"],
            owner_id=ctx[owner_key],
            resource_type=kind,
            title=title,
            is_public=public,
        )
    )
    s.flush()
    cfg_id = uuid.uuid4().hex
    s.add(Config(id=cfg_id, tenant_id=ctx["tenant"], kind=kind, item_id=item_id, current_version=1))
    s.add(ConfigRevision(tenant_id=ctx["tenant"], config_id=cfg_id, version=1, data=config))
    s.flush()
    return item_id


def _map(col):
    return {"kind": "map", "map": {"layers": [{"id": "l", "collectionId": col}]}}


def _seed(ctx):
    with ctx["Session"]() as s:
        s.add(
            Collection(
                id="parcelles",
                tenant_id=ctx["tenant"],
                owner_id=ctx["owner"],
                table_name="parcelles",
                title="Parcelles",
                pk_column="id",
                is_public=True,
            )
        )
        s.flush()
        ids = {
            "map1": _add_item(s, ctx, "map", "Carte 1", _map("parcelles"), public=True),
            "map2": _add_item(s, ctx, "map", "Carte 2", _map("parcelles"), public=True),
            "secret": _add_item(s, ctx, "map", "Carte secrète", _map("parcelles")),  # non lisible
        }
        ids["pipe"] = _add_item(
            s,
            ctx,
            "pipeline",
            "Pipeline",
            {
                "kind": "pipeline",
                "pipeline": {
                    "nodes": [
                        {
                            "id": "r",
                            "op": "reader.collection",
                            "params": {"collectionId": "parcelles"},
                        }
                    ]
                },
            },
            public=True,
        )
        ids["ds"] = _add_item(
            s,
            ctx,
            "dataset",
            "Dataset",
            {"kind": "dataset", "dataset": {"source": "collection", "collectionId": "parcelles"}},
            public=True,
        )
        ids["app"] = _add_item(
            s,
            ctx,
            "app",
            "Application",
            {"kind": "app", "dataSources": [{"id": "d", "datasetId": ids["ds"]}]},
            public=True,
        )
        ids["alert"] = _add_item(
            s,
            ctx,
            "alert",
            "Alerte",
            {"kind": "alert", "alert": {"datasetItemId": ids["ds"]}},
            public=True,
        )
        s.commit()
        return ids


def _user(ctx, s, key):
    from app.users.models import User

    return s.get(User, ctx[key])


def test_collection_impact_lists_visible_dependents_and_counts_hidden(world):
    ids = _seed(world)
    with world["Session"]() as s:
        res = service.impact(s, _user(world, s, "viewer"), ("collection", "parcelles"))
    by_title = {d["title"]: d for d in res["dependents"]}
    # 2 cartes + 1 pipeline + dataset directs ; application et alerte transitives (via dataset)
    assert {"Carte 1", "Carte 2", "Pipeline", "Dataset"} <= set(by_title)
    assert all(by_title[t]["direct"] for t in ("Carte 1", "Carte 2", "Pipeline", "Dataset"))
    assert not by_title["Application"]["direct"] and by_title["Application"]["depth"] == 2
    assert by_title["Alerte"]["depth"] == 2
    # la carte privée d'un autre : comptée, jamais nommée
    assert res["hiddenCount"] == 1
    assert "Carte secrète" not in json.dumps(res) and ids["secret"] not in json.dumps(res)


def test_owner_sees_every_dependent(world):
    _seed(world)
    with world["Session"]() as s:
        res = service.impact(s, _user(world, s, "owner"), ("collection", "parcelles"))
    assert res["hiddenCount"] == 0 and len(res["dependents"]) == 7


def test_lineage_has_upstream_downstream_and_edges(world):
    ids = _seed(world)
    with world["Session"]() as s:
        res = service.lineage(s, _user(world, s, "owner"), ("item", ids["ds"]))
    directions = {n["title"]: n["direction"] for n in res["nodes"]}
    assert directions["Parcelles"] == "upstream"
    assert directions["Application"] == directions["Alerte"] == "downstream"
    edges = {(e["from"]["id"], e["to"]["id"]) for e in res["edges"]}
    assert (ids["app"], ids["ds"]) in edges and (ids["ds"], "parcelles") in edges


def test_unreadable_hub_is_traversed_but_not_named(world):
    ids = _seed(world)
    with world["Session"]() as s:
        # dataset privé (illisible) : l'application publique qui en dépend reste visible
        s.get(Item, ids["ds"]).is_public = False
        s.commit()
        res = service.impact(s, _user(world, s, "viewer"), ("collection", "parcelles"))
    titles = {d["title"] for d in res["dependents"]}
    assert "Dataset" not in titles and {"Application", "Alerte"} <= titles
    assert res["hiddenCount"] == 2  # carte secrète + dataset


def test_graph_of_5000_items_under_one_second(world):
    with world["Session"]() as s:
        s.add(
            Collection(
                id="big",
                tenant_id=world["tenant"],
                owner_id=world["owner"],
                table_name="big",
                title="Big",
                pk_column="id",
                is_public=True,
            )
        )
        s.flush()
        for i in range(5000):
            _add_item(s, world, "map", f"M{i}", _map("big"), public=True)
        s.commit()
        user = _user(world, s, "viewer")
        start = time.perf_counter()
        res = service.impact(s, user, ("collection", "big"))
        elapsed = time.perf_counter() - start
    assert len(res["dependents"]) == 5000
    assert elapsed < 1.0, f"impact sur 5000 items : {elapsed:.2f}s"


def test_extract_refs_ignores_unknown_ids_and_self(world):
    ids = _seed(world)
    with world["Session"]() as s:
        _add_item(
            s, world, "app", "Orphan", {"kind": "app", "dataSources": [{"datasetId": "nope"}]}
        )
        s.commit()
        graph = service.build_graph(s, tenant_id=world["tenant"])
    assert graph.uses[("item", ids["app"])] == {("item", ids["ds"])}  # "nope" ignoré
    assert all(("item", "nope") not in v for v in graph.uses.values())


def _client(world, who):
    app = create_app()

    def override_session():
        with request_scoped_session(world["Session"]) as session:
            yield session

    with world["Session"]() as s:
        user = _user(world, s, who)
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    return TestClient(app)


def test_routes_return_impact_and_404_for_unreadable_target(world):
    ids = _seed(world)
    viewer = _client(world, "viewer")
    r = viewer.get("/v1/collections/parcelles/impact")
    assert r.status_code == 200 and r.json()["hiddenCount"] == 1
    r = viewer.get(f"/v1/items/{ids['ds']}/impact")
    assert {d["title"] for d in r.json()["dependents"]} == {"Application", "Alerte"}
    assert viewer.get(f"/v1/items/{ids['secret']}/impact").status_code == 404
    assert viewer.get("/v1/collections/absent/impact").status_code == 404
    lin = viewer.get(f"/v1/items/{ids['ds']}/lineage").json()
    assert {"from", "to"} <= set(lin["edges"][0])
