# SPDX-License-Identifier: Apache-2.0
"""Gabarits d'app/dashboard/site (ARC-26) — données déclaratives tenues en parité
avec le catalogue du shell (`shell/src/builder/templates.data.json`, copie
identique vérifiée par shell/src/builder/templates.test.ts). Sert à l'outil MCP
`create_item` avec `template` : même configuration que celle que l'utilisateur
obtient en choisissant le gabarit dans le catalogue du builder."""

import json
from pathlib import Path

from app.configs.schemas import BuilderConfig

_TEMPLATES: dict[str, dict] = {
    t["id"]: t
    for t in json.loads(
        (Path(__file__).parent / "builder_templates.json").read_text(encoding="utf-8")
    )
}


def template_ids() -> list[str]:
    return sorted(_TEMPLATES)


def build_config_from_template(template_id: str) -> BuilderConfig:
    """Config complète du gabarit. ValueError si l'id est inconnu. Reproduit ce
    que fait `createConfigItem` côté shell (page 1 d'un gabarit à pages)."""
    tpl = _TEMPLATES.get(template_id)
    if tpl is None:
        raise ValueError(f"unknown template '{template_id}' (known: {', '.join(template_ids())})")
    pages = tpl.get("pages") or []
    raw = {
        "version": 1,
        "kind": tpl["kind"],
        "theme": tpl.get("theme") or {},
        "dataSources": tpl.get("dataSources") or [],
        "layout": pages[0]["layout"] if pages else tpl["layout"],
        "messages": tpl.get("messages") or [],
        "pages": pages,
        "navigationMode": tpl.get("navigationMode", "tabs"),
        "interactions": "auto",
    }
    if tpl.get("printLayout"):
        raw["printLayout"] = tpl["printLayout"]
    return BuilderConfig.model_validate(raw)
