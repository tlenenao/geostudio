# SPDX-License-Identifier: Apache-2.0
"""Emprise spatiale d'un item `map`, persistée sur `Item` (SP-55 §2, GAP-06).

Ne duplique PAS une troisième implémentation de calcul d'emprise : réutilise
`app.collections.extent.table_extent` (déjà utilisé par `GET /collections/{id}`
et par l'import SP-6) sur chaque collection référencée par les couches
`vector`/`feature` de la config. Point de calcul UNIQUE (spec §2.3) : appelé
par les trois fonctions de bas niveau de `app.configs.repository`
(`create_config`, `update_config`, `rollback_config`) — jamais dupliqué côté
route HTTP ni côté outil MCP, pour éviter la classe de bug documentée dans
CLAUDE.md (« déjà rouvert trois fois » : REST -> MCP -> terrain3d/tileset3d).

Vit dans `app.configs` (pas `app.items`) : `app.items` est SOUS `app.configs`
dans le contrat de couches (`pyproject.toml::[tool.importlinter]`) et ne peut
donc pas importer `app.collections` (lui-même AU-DESSUS de `app.configs` —
`app.collections.dataset_validation`/`routes` importent déjà `app.configs`).
Le cycle de paquets qui en résulte (`app.collections -> app.configs ->
app.collections`) est le même genre que celui déjà documenté et nommément
excepté pour `app.analytics` — voir `ignore_imports` du contrat.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collections.extent import table_extent
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.collections.models import Collection
from app.configs.schemas import BuilderConfig
from app.items.models import Item

_BBOX_LAYER_KINDS = ("vector", "feature")


def _clear_bbox(item: Item) -> None:
    item.bbox_min_x = None
    item.bbox_min_y = None
    item.bbox_max_x = None
    item.bbox_max_y = None


def _union_bbox(a: list[float] | None, b: list[float]) -> list[float]:
    if a is None:
        return b
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def recompute_item_bbox(
    session: Session, *, item: Item, config: BuilderConfig, tenant_id: str
) -> None:
    if config.kind != "map" or config.map is None:
        _clear_bbox(item)
        return

    collection_ids = {
        layer.collectionId
        for layer in config.map.layers
        if layer.kind in _BBOX_LAYER_KINDS and layer.collectionId
    }

    union: list[float] | None = None
    for collection_id in collection_ids:
        collection = session.execute(
            select(Collection).where(
                Collection.id == collection_id, Collection.tenant_id == tenant_id
            )
        ).scalar_one_or_none()
        if collection is None:
            continue
        try:
            info = introspect_table(session, collection.table_name)
        except (TableNotFound, UnsupportedTable):
            # Collection référencée par la config mais table absente/invalide
            # (ex. supprimée hors-bande) — ignorée, pas une erreur bloquante
            # pour l'enregistrement de la config elle-même.
            continue
        layer_bbox = table_extent(session, info)
        if layer_bbox is None:
            continue
        union = _union_bbox(union, layer_bbox)

    if union is None:
        _clear_bbox(item)
    else:
        item.bbox_min_x, item.bbox_min_y, item.bbox_max_x, item.bbox_max_y = union
