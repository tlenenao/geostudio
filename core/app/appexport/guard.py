# SPDX-License-Identifier: Apache-2.0
"""Garde d'export (SP-18a/b) : refuse tout export dont une DataSource
référence une collection non publique. Le mode Statique (SP-18a) refuse en
plus les sources "statistics" (rien à figer côté serveur) et tout widget
hors de l'allowlist builtin (rien n'est bundlé au runtime, un widget tiers
serait introuvable). Le mode Connecté (SP-18b) n'a besoin d'aucune des deux
restrictions : "statistics" appelle /collections/{id}/aggregate en direct
au runtime (déjà anonyme-capable côté serveur pour une collection publique,
cf. app/features/routes.py's get_current_user_optional), et un widget tiers
charge son JS depuis son URL d'origine exactement comme dans le shell
normal — rien n'est bundlé, donc rien à interdire."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.schemas import BuilderConfig

# Miroir de shell/src/builder/widgets/{index,data,chart,pivot,navigation,
# form,hero,richSection,gallery,datasetCard,dateRangeFilter,selectFilter,
# sliderFilter,tabs,modal,drawer,filter,mapWidget,indicator}.tsx — à tenir
# en phase manuellement (pas de génération partagée TS/Python), même
# discipline que l'allowlist QGIS (SP-15d) ou les champs AggregateRequestBody.
# Uniquement pertinent en mode Statique (mode="static") — cf. docstring.
_SUPPORTED_WIDGET_TYPES = frozenset({
    "text", "image", "button", "table", "list", "map", "indicator", "chart",
    "pivot", "nav", "form", "hero", "richSection", "gallery", "datasetCard",
    "dateRangeFilter", "selectFilter", "sliderFilter", "tabs", "modal",
    "drawer", "filter",
})


@dataclass
class ExportGuardResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def _collect_widget_types(config: BuilderConfig) -> set[str]:
    types: set[str] = set()
    # A config always has at least one page. If `pages` is empty (legacy /
    # implicit single-page shape, cf. shell/src/builder/pages.ts:6-7,23),
    # the widgets actually live in the top-level `layout` — scan both so a
    # single-page app (the common case) doesn't sail through unchecked.
    if config.layout is not None:
        for item in config.layout.items:
            types.add(item.widget)
    for page in config.pages:
        for item in page.layout.items:
            types.add(item.widget)
    return types


def check_export_guard(
    session: Session, *, tenant_id: str, config: BuilderConfig, mode: str,
) -> ExportGuardResult:
    reasons: list[str] = []

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
        # "features" (les deux modes) et "statistics" en mode connecté :
        # même garde is_public — le mode connecté appelle
        # /collections/{id}/aggregate en direct au runtime au lieu de figer
        # un résultat côté serveur.
        collection_id = source.layer
        col = collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=collection_id)
        if col is None:
            reasons.append(f"source '{source.id}' : collection '{collection_id}' introuvable")
            continue
        facts = collections_repo.get_access_facts(col)
        if not facts.is_public:
            reasons.append(
                f"source '{source.id}' : collection '{collection_id}' n'est pas partagée publiquement"
            )

    if mode == "static":
        unsupported = _collect_widget_types(config) - _SUPPORTED_WIDGET_TYPES
        for widget_type in sorted(unsupported):
            reasons.append(
                f"widget '{widget_type}' non supporté par l'export statique "
                "(extension tierce, non prise en charge)"
            )

    return ExportGuardResult(allowed=not reasons, reasons=reasons)
