# SPDX-License-Identifier: Apache-2.0
"""Validation sémantique des documents de config à l'ÉCRITURE seulement (P21 :
c08-002, j03-011, j04-013). Volontairement hors des modèles Pydantic de
app.configs.schemas : ces modèles sont aussi relus depuis la base, et une
borne qui y vivrait rendrait illisible toute config déjà enregistrée.

Appelée par POST /configs (create_config_service, donc aussi les outils MCP
créateurs), PUT /configs/{id}, PUT /configs/by-item/{id} et save_app_config
(MCP). Pas par /rollback : une révision ancienne peut légitimement violer une
règle ajoutée depuis."""

from datetime import date
from urllib.parse import urlparse

import celpy
from celpy.celparser import CELParseError
from fastapi import HTTPException

from app.configs.schemas import BuilderConfig, LayoutItem, MapConfig

_CEL_ENV = celpy.Environment()


def _cel_syntax_error(expr: str) -> str | None:
    """Contrôle syntaxique d'une expression CEL par le parseur cel-python
    (REV-278b ; remplace le contrôle de parenthèses). Syntaxe seulement : les
    identifiants inconnus et les erreurs de type restent détectés à
    l'évaluation par le shell (cel-js), qui est le moteur d'exécution."""
    if not expr.strip():
        return "empty expression"
    try:
        _CEL_ENV.compile(expr)
    except CELParseError as exc:
        where = f" at column {exc.column}" if exc.column else ""
        return f"invalid CEL{where}"
    return None


def _http_url_error(name: str, value: str | None) -> str | None:
    if value and urlparse(value).scheme not in ("http", "https"):
        return f"{name} must be an http(s) URL"
    return None


def _map_errors(m: MapConfig) -> list[str]:
    errs: list[str] = []
    lon, lat = m.view.center
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        errs.append("map.view.center must be [lon in -180..180, lat in -90..90]")
    if not 0 <= m.view.zoom <= 24:
        errs.append("map.view.zoom must be within 0..24")
    if m.view.pitch is not None and not 0 <= m.view.pitch <= 85:
        errs.append("map.view.pitch must be within 0..85")
    for i, layer in enumerate(m.layers):
        at = f"map.layers[{i}]"
        if layer.opacity is not None and not 0 <= layer.opacity <= 1:
            errs.append(f"{at}.opacity must be within 0..1")
        for name in ("tilesUrl", "url", "dataUrl"):
            e = _http_url_error(f"{at}.{name}", getattr(layer, name))
            if e:
                errs.append(e)
        # Un kind sans sa source ne rend rien. Les couches `vector` liées à une
        # collection reçoivent leur tilesUrl/sourceLayer du cœur (SP-24).
        if layer.kind == "vector" and not layer.collectionId:
            if not layer.tilesUrl or not layer.sourceLayer:
                errs.append(f"{at}: vector layer requires tilesUrl and sourceLayer")
        elif layer.kind == "raster" and not layer.tilesUrl:
            errs.append(f"{at}: raster layer requires tilesUrl")
        elif layer.kind == "deck" and not layer.dataUrl:
            errs.append(f"{at}: deck layer requires dataUrl")
        elif layer.kind in ("feature", "tiles3d") and not layer.url:
            errs.append(f"{at}: {layer.kind} layer requires url")
    return errs


# REV-104 : bornes des props du widget timePlayer (lecteur temporel). Les
# props de widget sont un dict non typé (LayoutItem.props) : bornes à
# l'écriture seulement, comme le reste de ce module.
_TIME_PLAYER_INT_BOUNDS = {
    "stepDays": (1, 3660),
    "windowDays": (1, 3660),
    "intervalMs": (500, 10000),
}


def _time_player_errors(props: dict, name: str) -> list[str]:
    errs: list[str] = []
    dates: dict[str, date] = {}
    for key in ("from", "to"):
        value = props.get(key)
        if value in (None, ""):
            continue
        # Strict format: YYYY-MM-DD only (length check + fromisoformat)
        if not isinstance(value, str) or len(value) != 10:
            errs.append(f"widget '{name}' {key}: must be an ISO date (YYYY-MM-DD)")
            continue
        try:
            dates[key] = date.fromisoformat(value)
        except (TypeError, ValueError):
            errs.append(f"widget '{name}' {key}: must be an ISO date (YYYY-MM-DD)")
    if len(dates) == 2 and dates["from"] > dates["to"]:
        errs.append(f"widget '{name}': from must be <= to")
    for key, (lo, hi) in _TIME_PLAYER_INT_BOUNDS.items():
        value = props.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            errs.append(f"widget '{name}' {key}: must be an integer within {lo}..{hi}")
    return errs


def _item_errors(item: LayoutItem, seen: set[str]) -> list[str]:
    errs: list[str] = []
    name = item.id or item.widget
    if item.id is not None:
        if item.id in seen:
            errs.append(f"duplicate widget id '{item.id}'")
        seen.add(item.id)
    if item.w < 1 or item.h < 1 or item.x < 0 or item.y < 0:
        errs.append(f"widget '{name}': w/h must be >= 1 and x/y >= 0")
    if item.visibleWhen is not None and (e := _cel_syntax_error(item.visibleWhen)):
        errs.append(f"widget '{name}' visibleWhen: {e}")
    if item.widget == "timePlayer":
        errs += _time_player_errors(item.props, name)
    return errs


def widget_nodes(node: object) -> list[dict]:
    """Tous les nœuds widget (dict portant `widget: str`, `id` optionnel) d'un
    arbre de layout, imbriqués compris (props.items d'une modale/d'un
    tiroir) — REV-278a/c."""
    nodes: list[dict] = []
    if isinstance(node, dict):
        if isinstance(node.get("widget"), str):
            nodes.append(node)
        for value in node.values():
            nodes += widget_nodes(value)
    elif isinstance(node, list):
        for value in node:
            nodes += widget_nodes(value)
    return nodes


def _widget_ids(node: object) -> set[str]:
    return {n["id"] for n in widget_nodes(node) if isinstance(n.get("id"), str)}


def _layout_errors(config: BuilderConfig) -> list[str]:
    errs: list[str] = []
    layouts = ([config.layout] if config.layout else []) + [p.layout for p in config.pages]
    for lay in layouts:
        seen: set[str] = set()
        for item in lay.items:
            errs += _item_errors(item, seen)
    widgets = _widget_ids([lay.model_dump() for lay in layouts])
    targets = widgets | {f"var:{v.id}" for v in config.variables}
    on_enter = [m for p in config.pages for m in p.onEnter]
    for m in list(config.messages) + on_enter:
        name = m.id or m.event
        if m.when is not None and (e := _cel_syntax_error(m.when)):
            errs.append(f"message '{name}' when: {e}")
        if m.to not in targets:
            errs.append(f"message '{name}' to: unknown target '{m.to}'")
    for m in config.messages:  # le from d'un onEnter est l'id de la page
        if m.from_ not in widgets:
            errs.append(f"message '{m.id or m.event}' from: unknown widget '{m.from_}'")
    return errs


def validate_document(config: BuilderConfig) -> None:
    errs = _layout_errors(config)
    if config.map is not None:
        errs += _map_errors(config.map)
    if errs:
        raise HTTPException(status_code=422, detail="; ".join(errs))
