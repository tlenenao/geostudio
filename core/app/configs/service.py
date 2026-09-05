# SPDX-License-Identifier: Apache-2.0
"""Couche de service pour la création de configs — extraite de
POST /configs (app/configs/routes.py::create_config) pour être appelée à la
fois par la route REST et par tout tool MCP créateur de config
(create_item/create_form_app/create_dataset/create_bookmark/create_pipeline,
app/mcp/tools/configs.py|dataset.py|bookmark.py|pipelines.py) — SP-43 Étape 8.

Chaque validateur par kind ci-dessous (dataset_validation,
bookmark_validation, pipeline_validation, alert_validation,
report_validation, tileset3d_validation, terrain3d_validation) est un no-op
pour tout kind différent du sien (vérifié par lecture directe de chacun
avant d'écrire ce service) : appeler systématiquement la séquence complète,
quel que soit le kind soumis par l'appelant, préserve le comportement de
chaque tool MCP qui n'en appelait jusqu'ici qu'un sous-ensemble — aucun
n'est donc "corrigé" ou "durci" par cette extraction, juste rendu commun.

Ce service n'écrit PAS l'audit (contrairement à create_config avant cette
extraction) : chaque appelant (route REST, chaque tool MCP créateur) écrit
ses propres lignes d'audit après l'appel, avec son propre actor_kind et son
propre payload — certains tools (create_form_app notamment) ont un payload
d'audit domaine-spécifique qui ne correspond pas au payload générique
{"title", "kind"} de create_config ; les fusionner dans ce service aurait
changé silencieusement le contenu du journal d'audit de ces tools, un vrai
risque de régression que cette séparation évite."""

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.dependency import is_etl_enabled, is_export_enabled
from app.configs import repository as repo
from app.configs.alert_validation import validate_alert_payload
from app.configs.bookmark_validation import validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload
from app.configs.extension_permissions import (
    ExtensionPermissionError,
    validate_extension_permissions,
)
from app.configs.pipeline_validation import validate_pipeline_payload
from app.configs.report_validation import validate_report_payload
from app.configs.repository import ConfigRead
from app.configs.schemas import BuilderConfig
from app.configs.terrain3d_validation import validate_terrain3d_payload
from app.configs.tileset3d_validation import validate_tileset3d_payload
from app.items import repository as items_repo
from app.items.models import Item
from app.items.slug import InvalidSlugError, SlugCollisionError
from app.roles.guards import require_privilege
from app.roles.kind_registry import privilege_for_kind
from app.users.models import User


@dataclass
class CreatedConfig:
    item: Item
    config: ConfigRead


# Ces 3 gardes (_require_etl_enabled_for_pipeline, _require_export_enabled_for_report,
# _validate_extension_scope) sont importées telles quelles par app.configs.routes
# (PUT /configs/{id}, /rollback) — revue finale SP-43 (Important I1) : Task 9 avait
# recréé ici des copies byte-équivalentes de fonctions déjà définies dans routes.py,
# rouvrant la classe de défaut "même règle à N sites" que SP-43 devait fermer. Ne pas
# redupliquer : toute future modification de ces 3 gardes doit se faire ici, seule
# source de vérité, aussi bien pour le chemin create (POST /configs, tools MCP
# créateurs) que pour le chemin update (PUT /configs/{id}, /rollback).
def _require_etl_enabled_for_pipeline(config: BuilderConfig) -> None:
    if config.kind == "pipeline" and not is_etl_enabled():
        raise HTTPException(status_code=403, detail="ETL capability disabled on this instance")


def _require_export_enabled_for_report(config: BuilderConfig) -> None:
    # Jumeau de la garde pipeline/ETL ci-dessus (revue finale SP-17b, I3) :
    # sur une instance sans capacité export, un ReportSchedule pouvait être
    # créé mais son rendu restait "pending" à jamais — rien ne dépile la file
    # `export`, et export_repo.reclaim_stuck_jobs ne récupère que les
    # "running". Mieux vaut refuser la création tout de suite.
    if config.kind == "report" and not is_export_enabled():
        raise HTTPException(status_code=403, detail="Export capability disabled on this instance")


def _validate_extension_scope(session: Session, config: BuilderConfig, *, tenant_id: str) -> None:
    try:
        validate_extension_permissions(session, config, tenant_id=tenant_id)
    except ExtensionPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


def create_config_service(
    session: Session,
    config: BuilderConfig,
    *,
    title: str,
    user: User,
    slug: str | None = None,
) -> CreatedConfig:
    """Extrait de app/configs/routes.py::create_config (POST /configs) —
    même séquence de gardes/validateurs, identique pour la route REST et
    pour tout tool MCP créateur de config. N'écrit pas l'audit (cf.
    docstring du module) : le retour porte l'item et la config créés, à
    l'appelant d'écrire ses propres lignes d'audit."""
    require_privilege(session, user, privilege_for_kind(config.kind))
    _require_etl_enabled_for_pipeline(config)
    _require_export_enabled_for_report(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    validate_dataset_payload(session, config, user=user)
    validate_bookmark_payload(session, config, user=user)
    validate_pipeline_payload(session, config, user=user)
    validate_alert_payload(session, config, user=user)
    validate_report_payload(session, config, user=user)
    validate_tileset3d_payload(session, config, user=user)
    validate_terrain3d_payload(session, config, user=user)
    try:
        item = items_repo.create_item(
            session,
            tenant_id=user.tenant_id,
            owner_id=user.id,
            resource_type=config.kind,
            title=title,
            slug=slug,
        )
    except SlugCollisionError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except InvalidSlugError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    result = repo.create_config(session, config, item_id=item.id, tenant_id=user.tenant_id)
    return CreatedConfig(item=item, config=result)
