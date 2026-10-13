# SPDX-License-Identifier: Apache-2.0
"""Lineage et vue d'impact (ARC4-F15) : graphe de dépendances DÉRIVÉ des configs,
calculé à la demande — aucune table. Un nœud est un item (`item`) ou une collection
(`collection`) ; une arête `A -> B` signifie « A utilise B » (carte -> collection,
dataset -> collection/pipeline, application -> dataset, alerte -> dataset, rapport ->
bookmark, pipeline -> collection…).

Les références sont repérées par NOM de clé dans le JSON de la config courante (le
schéma est trop large pour un parcours typé : widgets libres, params d'op) et ne sont
retenues que si l'identifiant désigne réellement un item ou une collection du tenant.

Visibilité : un dépendant que l'utilisateur ne peut pas lire est COMPTÉ (`hiddenCount`)
sans jamais être nommé, mais il reste traversé pour que les dépendants transitifs
visibles et le compte restent exacts."""

from collections import deque
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.collections.models import Collection
from app.configs.models import Config, ConfigRevision
from app.items.models import Item
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.sharing.authorization import decide
from app.sharing.repository import roles_for_collections, roles_for_items
from app.users.models import User

# clés de config qui portent un identifiant d'item ou de collection
REF_KEYS = frozenset(
    {
        "collectionId",
        "withCollectionId",
        "datasetId",
        "datasetItemId",
        "targetDatasetId",
        "arcgisItemId",
        "sourcePipelineId",
        "pipelineItemId",
        "pipelineId",
        "mapId",
        "mapItemId",
        "bookmarkItemId",
        "appId",
        "itemId",
    }
)

NodeKey = tuple[str, str]  # ("item" | "collection", id)


@dataclass(frozen=True)
class Graph:
    titles: dict[NodeKey, str]
    kinds: dict[NodeKey, str]  # resource_type d'un item, "collection" sinon
    uses: dict[NodeKey, set[NodeKey]]  # A -> {B} : A utilise B
    used_by: dict[NodeKey, set[NodeKey]]  # B -> {A}


def extract_refs(node: Any, out: set[str] | None = None) -> set[str]:
    """Valeurs de REF_KEYS (str) trouvées n'importe où dans le JSON `node`."""
    out = set() if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            if k in REF_KEYS and isinstance(v, str) and v:
                out.add(v)
            else:
                extract_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            extract_refs(v, out)
    return out


def build_graph(session: Session, *, tenant_id: str) -> Graph:
    titles: dict[NodeKey, str] = {}
    kinds: dict[NodeKey, str] = {}
    for item_id, title, rtype in session.execute(
        select(Item.id, Item.title, Item.resource_type).where(Item.tenant_id == tenant_id)
    ):
        titles[("item", item_id)] = title
        kinds[("item", item_id)] = rtype
    for col_id, title in session.execute(
        select(Collection.id, Collection.title).where(Collection.tenant_id == tenant_id)
    ):
        titles[("collection", col_id)] = title
        kinds[("collection", col_id)] = "collection"

    uses: dict[NodeKey, set[NodeKey]] = {}
    used_by: dict[NodeKey, set[NodeKey]] = {}
    rows = session.execute(
        select(Config.item_id, ConfigRevision.data)
        .join(
            ConfigRevision,
            and_(
                ConfigRevision.config_id == Config.id,
                ConfigRevision.version == Config.current_version,
            ),
        )
        .where(Config.tenant_id == tenant_id)
    )
    for item_id, data in rows:
        src: NodeKey = ("item", item_id)
        for ref in extract_refs(data):
            for dst in (("item", ref), ("collection", ref)):
                if dst in titles and dst != src:
                    uses.setdefault(src, set()).add(dst)
                    used_by.setdefault(dst, set()).add(src)
    return Graph(titles, kinds, uses, used_by)


def _walk(adj: dict[NodeKey, set[NodeKey]], start: NodeKey) -> dict[NodeKey, int]:
    """Parcours en largeur : profondeur minimale de chaque nœud atteignable (≠ start)."""
    depth = {start: 0}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in adj.get(cur, ()):
            if nxt not in depth:
                depth[nxt] = depth[cur] + 1
                queue.append(nxt)
    del depth[start]
    return depth


def visible_nodes(session: Session, user: User, nodes: set[NodeKey]) -> set[NodeKey]:
    """Sous-ensemble de `nodes` que `user` peut lire (deux requêtes de rôles en tout)."""
    item_ids = [i for t, i in nodes if t == "item"]
    col_ids = [i for t, i in nodes if t == "collection"]
    visible: set[NodeKey] = set()
    if item_ids:
        roles = roles_for_items(
            session, tenant_id=user.tenant_id, user_id=user.id, item_ids=item_ids
        )
        for row in session.execute(
            select(Item.id, Item.owner_id, Item.is_public, Item.is_published).where(
                Item.tenant_id == user.tenant_id, Item.id.in_(item_ids)
            )
        ):
            if decide(
                action="read",
                kind="item",
                is_owner=row.owner_id == user.id,
                is_public=row.is_public,
                is_published=row.is_published,
                roles=roles.get(row.id, frozenset()),
                actor_is_admin=False,
            ):
                visible.add(("item", row.id))
    if col_ids:
        admin = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        roles = roles_for_collections(
            session, tenant_id=user.tenant_id, user_id=user.id, collection_ids=col_ids
        )
        for row in session.execute(
            select(Collection.id, Collection.owner_id, Collection.is_public).where(
                Collection.tenant_id == user.tenant_id, Collection.id.in_(col_ids)
            )
        ):
            if admin or decide(
                action="read",
                kind="collection",
                is_owner=row.owner_id == user.id,
                is_public=row.is_public,
                is_published=False,
                roles=roles.get(row.id, frozenset()),
                actor_is_admin=False,
            ):
                visible.add(("collection", row.id))
    return visible


def _node(graph: Graph, key: NodeKey, **extra) -> dict:
    return {
        "type": key[0],
        "id": key[1],
        "title": graph.titles[key],
        "resourceType": graph.kinds[key],
        **extra,
    }


def impact(session: Session, user: User, target: NodeKey, *, graph: Graph | None = None) -> dict:
    """Dépendants (transitifs) de `target` : ce qui casserait s'il disparaissait."""
    graph = graph or build_graph(session, tenant_id=user.tenant_id)
    depths = _walk(graph.used_by, target)
    visible = visible_nodes(session, user, set(depths))
    shown = sorted(
        (k for k in depths if k in visible), key=lambda k: (depths[k], graph.titles[k].lower())
    )
    return {
        "target": _node(graph, target),
        "dependents": [_node(graph, k, depth=depths[k], direct=depths[k] == 1) for k in shown],
        "hiddenCount": len(depths) - len(shown),
    }


def lineage(session: Session, user: User, target: NodeKey, *, graph: Graph | None = None) -> dict:
    """Amont (ce que `target` utilise) et aval (ce qui l'utilise), avec les arêtes entre
    nœuds visibles (`from` utilise `to`)."""
    graph = graph or build_graph(session, tenant_id=user.tenant_id)
    upstream = _walk(graph.uses, target)
    downstream = _walk(graph.used_by, target)
    visible = visible_nodes(session, user, set(upstream) | set(downstream))
    nodes = {k: "upstream" for k in upstream if k in visible}
    nodes.update({k: "downstream" for k in downstream if k in visible})
    members = {target, *nodes}
    edges = sorted((a, b) for a in members for b in graph.uses.get(a, ()) if b in members)
    return {
        "target": _node(graph, target),
        "nodes": [_node(graph, k, direction=d) for k, d in nodes.items()],
        "edges": [
            {"from": {"type": a[0], "id": a[1]}, "to": {"type": b[0], "id": b[1]}} for a, b in edges
        ],
        "hiddenCount": len(set(upstream) | set(downstream)) - len(nodes),
    }
