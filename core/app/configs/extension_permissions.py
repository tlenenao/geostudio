from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig, LayoutItem
from app.extensions.models import Extension


class ExtensionPermissionError(Exception):
    def __init__(self, widget: str, prop: str, collection: str) -> None:
        self.widget = widget
        self.prop = prop
        self.collection = collection
        super().__init__(
            f"widget '{widget}' prop '{prop}': collection '{collection}' is outside its declared permissions"
        )


def _all_layout_items(config: BuilderConfig) -> list[LayoutItem]:
    items: list[LayoutItem] = []
    if config.layout:
        items.extend(config.layout.items)
    for page in config.pages:
        items.extend(page.layout.items)
    return items


def validate_extension_permissions(session: Session, config: BuilderConfig, *, tenant_id: str) -> None:
    items = _all_layout_items(config)
    widget_types = {item.widget for item in items}
    if not widget_types:
        return
    extensions = {
        ext.id: ext
        for ext in session.scalars(
            select(Extension).where(Extension.tenant_id == tenant_id, Extension.id.in_(widget_types))
        )
    }
    if not extensions:
        return
    data_sources_by_id = {ds.id: ds for ds in config.dataSources}
    for item in items:
        ext = extensions.get(item.widget)
        if ext is None:
            continue
        allowed = ext.permissions.get("collections", "all")
        if allowed == "all":
            continue
        data_source_props = {p["name"] for p in ext.props if p["type"] == "dataSource"}
        for prop_name in data_source_props:
            value = item.props.get(prop_name)
            if not value:
                continue
            source = data_sources_by_id.get(value)
            if source is None:
                continue
            if source.layer not in allowed:
                raise ExtensionPermissionError(item.widget, prop_name, source.layer)
