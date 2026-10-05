# SPDX-License-Identifier: Apache-2.0
"""Garde d'export (SP-18a/b/c) : refuse tout export dont une DataSource
référence une collection non publique. Le mode Statique (SP-18a) refuse en
plus les sources "statistics" (rien à figer côté serveur) et tout widget
hors de l'allowlist builtin (rien n'est bundlé au runtime, un widget tiers
serait introuvable). Le mode Connecté (SP-18b) n'a besoin d'aucune des deux
restrictions : "statistics" appelle /collections/{id}/aggregate en direct
au runtime (déjà anonyme-capable côté serveur pour une collection publique,
cf. app/features/routes.py's get_current_user_optional), et un widget tiers
charge son JS depuis son URL d'origine exactement comme dans le shell
normal — rien n'est bundlé, donc rien à interdire. Le mode Autoporté
(SP-18c) combine les deux axes indépendamment : is_public lenient comme
Connecté ("statistics" pleinement supporté, figé dans l'instantané et
interrogé via /aggregate par le mini-serveur), MAIS allowlist de widgets
stricte comme Statique (rien n'est bundlé ici non plus — décision prise en
session 2026-08-15, cf. design SP-18c §3.3 : aucune tentative de bundling
offline de widgets tiers)."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.schemas import BuilderConfig

# Miroir de shell/src/builder/widgets/{index,data,chart,pivot,navigation,
# form,hero,richSection,gallery,datasetCard,dateRangeFilter,selectFilter,
# sliderFilter,tabs,modal,drawer,filter,mapWidget,indicator}.tsx — à tenir
# en phase manuellement (pas de génération partagée TS/Python), même
# discipline que l'allowlist QGIS (SP-15d) ou les champs AggregateRequestBody.
# Pertinent pour mode="static" ET mode="standalone" — cf. docstring.
_SUPPORTED_WIDGET_TYPES = frozenset(
    {
        "text",
        "image",
        "button",
        "table",
        "list",
        "map",
        "indicator",
        "chart",
        "pivot",
        "nav",
        "form",
        "hero",
        "richSection",
        "gallery",
        "datasetCard",
        "dateRangeFilter",
        "selectFilter",
        "sliderFilter",
        "tabs",
        "modal",
        "drawer",
        "filter",
        "variableInput",
        "timePlayer",
    }
)

# Seuls ces kinds sont des apps rendues par AppRenderer (j10b-007) : un site,
# une alerte ou un pipeline exportés donneraient un bundle sans sens.
EXPORTABLE_KINDS = frozenset({"app", "dashboard"})

_STRICT_WIDGET_MODES = frozenset({"static", "standalone"})


@dataclass
class ExportGuardResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def _nested_widget_types(value, types: set[str]) -> None:
    # tabs (props.tabs[].items), modal/drawer (props.items) : les widgets
    # imbriqués vivent dans LayoutItem.props (dict libre) — parcours générique
    # de tout dict portant une clé "widget", sans connaître la forme de chaque
    # conteneur (j10b-004).
    if isinstance(value, dict):
        if isinstance(value.get("widget"), str):
            types.add(value["widget"])
        for v in value.values():
            _nested_widget_types(v, types)
    elif isinstance(value, list):
        for v in value:
            _nested_widget_types(v, types)


def _collect_widget_types(config: BuilderConfig) -> set[str]:
    types: set[str] = set()
    # A config always has at least one page. If `pages` is empty (legacy /
    # implicit single-page shape, cf. shell/src/builder/pages.ts:6-7,23),
    # the widgets actually live in the top-level `layout` — scan both so a
    # single-page app (the common case) doesn't sail through unchecked.
    layouts = [p.layout for p in config.pages]
    if config.layout is not None:
        layouts.append(config.layout)
    for layout in layouts:
        for item in layout.items:
            types.add(item.widget)
            _nested_widget_types(item.props, types)
    return types


def check_export_guard(
    session: Session,
    *,
    tenant_id: str,
    config: BuilderConfig,
    mode: str,
) -> ExportGuardResult:
    reasons: list[str] = []

    if config.kind not in EXPORTABLE_KINDS:
        reasons.append(f"un item de kind '{config.kind}' n'est pas exportable (app/dashboard)")

    for source in config.dataSources:
        if source.type == "static":
            continue
        if source.type == "statistics" and mode == "static":
            reasons.append(
                f"source '{source.id}' : l'export statique ne supporte pas encore "
                "les sources de type agrégat (statistics)"
            )
            continue
        if source.type not in ("features", "statistics"):
            reasons.append(f"source '{source.id}' : type '{source.type}' non supporté")
            continue
        # "features" (tous modes) et "statistics" en mode connecté/autoporté :
        # même garde is_public — connecté appelle /collections/{id}/aggregate
        # en direct au runtime, autoporté le fige dans l'instantané et le
        # sert depuis le mini-serveur ; aucun des deux n'a besoin de figer
        # un résultat au moment de l'export lui-même.
        collection_id = source.layer
        col = collections_repo.get_collection(
            session, tenant_id=tenant_id, collection_id=collection_id
        )
        if col is None:
            reasons.append(f"source '{source.id}' : collection '{collection_id}' introuvable")
            continue
        facts = collections_repo.get_access_facts(col)
        if not facts.is_public:
            reasons.append(
                f"source '{source.id}' : collection '{collection_id}' n'est pas "
                "partagée publiquement"
            )

    if mode in _STRICT_WIDGET_MODES:
        unsupported = _collect_widget_types(config) - _SUPPORTED_WIDGET_TYPES
        for widget_type in sorted(unsupported):
            reasons.append(
                f"widget '{widget_type}' non supporté par ce mode d'export "
                "(extension tierce, non prise en charge)"
            )

    elif "addressSearch" in _collect_widget_types(config):
        # /v1/geocode exige un utilisateur authentifié (REV-102) : inutilisable
        # depuis un export connecté anonyme. (Modes stricts : déjà hors allowlist.)
        reasons.append(
            "widget 'addressSearch' non supporté par l'export connecté (géocodage authentifié)"
        )

    return ExportGuardResult(allowed=not reasons, reasons=reasons)
