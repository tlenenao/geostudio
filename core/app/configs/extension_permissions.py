# SPDX-License-Identifier: Apache-2.0
"""`permissions.collections` d'une extension borne les sources de données
passées à son widget. Ce n'est PAS une sandbox : le code tiers s'exécute avec
la session de l'utilisateur et peut appeler l'API lui-même (AUD-108)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.document_validation import widget_nodes
from app.configs.schemas import BuilderConfig, DataSource
from app.extensions.models import Extension


class ExtensionPermissionError(Exception):
    def __init__(self, widget: str, prop: str, collection: str) -> None:
        self.widget = widget
        self.prop = prop
        self.collection = collection
        super().__init__(
            f"widget '{widget}' prop '{prop}': collection '{collection}' is outside "
            "its declared permissions"
        )


def _source_collection(session: Session, source: DataSource) -> str | None:
    """Collection réellement lue par une source : `layer`, ou la collection du
    dataset référencé (AUD-108) ; None si elle ne se résout pas."""
    if source.layer:
        return source.layer
    if source.datasetId:
        cfg = configs_repo.get_config_by_item(session, source.datasetId)
        dataset = cfg.config.dataset if cfg is not None and cfg.kind == "dataset" else None
        if dataset is not None and dataset.source == "collection":
            return dataset.collectionId
    return None


def validate_extension_permissions(
    session: Session, config: BuilderConfig, *, tenant_id: str
) -> None:
    nodes = widget_nodes(config.model_dump(mode="json"))  # imbriqués compris (AUD-108)
    widget_types = {n["widget"] for n in nodes}
    if not widget_types:
        return
    extensions = {
        ext.id: ext
        for ext in session.scalars(
            select(Extension).where(
                Extension.tenant_id == tenant_id, Extension.id.in_(widget_types)
            )
        )
    }
    if not extensions:
        return
    data_sources_by_id = {ds.id: ds for ds in config.dataSources}
    for node in nodes:
        ext = extensions.get(node["widget"])
        if ext is None:
            continue
        allowed = ext.permissions.get("collections", "all")
        if allowed == "all":
            continue
        props = node.get("props") or {}
        # dataSourceId est lu par WidgetHost quel que soit le manifeste (AUD-108).
        names = {p["name"] for p in ext.props if p["type"] == "dataSource"} | {"dataSourceId"}
        for prop_name in sorted(names):
            value = props.get(prop_name)
            if value in (None, ""):
                continue
            if not isinstance(value, str):
                raise ExtensionPermissionError(node["widget"], prop_name, "<expression>")
            source = data_sources_by_id.get(value)
            if source is not None and source.type == "static":
                continue
            collection = _source_collection(session, source) if source is not None else None
            if collection is None or collection not in allowed:
                raise ExtensionPermissionError(node["widget"], prop_name, collection or value)
