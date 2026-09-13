# SPDX-License-Identifier: Apache-2.0
"""Autorisation invité (GAP-19) : un jeton de lien de partage (SP-54,
app.sharing.share_links) autorise, en plus de la lecture de l'item racine,
la lecture des collections que sa config référence comme sources de
données. Chemin PARALLÈLE à app.sharing.authorization.can() — jamais une
modification de can()/decide()/get_current_user. Vit dans app.configs (pas
app.sharing) car la résolution de portée a besoin de lire BuilderConfig/
DataSource (app.configs.schemas) et get_config_by_item
(app.configs.repository) — app.sharing est EN DESSOUS d'app.configs dans le
contrat de couches (core/pyproject.toml) et ne peut donc pas les importer.
Même patron qu'app.configs.bbox (SP-55/GAP-06), même raison structurelle.

Invariant de sécurité central (vérifié par
tests/test_configs_guest_access.py::
test_resolve_guest_scope_rejects_a_dataset_id_from_another_tenant) : un
DataSource.datasetId n'est suivi QUE si get_access_facts(tenant_id=
claims.tenant_id, ...) le trouve dans le MÊME tenant que l'item racine — un
identifiant recopié depuis un autre tenant (import, copier-coller) ne donne
jamais accès à son item ni à sa collection.

Second invariant de sécurité, ajouté après une revue finale de branche qui a
démontré par preuve directe (PoC en session) un contournement réel de can() :
la portée résolue ci-dessous (`allowed_item_ids`/`allowed_collection_ids`)
n'est PAS elle-même une autorisation — un auteur de config peut y faire
figurer n'importe quel `layer`/`datasetId` du tenant sans que rien ne
vérifie qu'il a lui-même le droit de lire cette ressource. `GuestActor`
porte donc aussi `created_by` (le créateur du ShareLink, jamais l'auteur de
la config, qui peut différer) : les points d'appel (get_readable_collection,
get_config_by_item) DOIVENT recouper la portée avec can(session,
user_id=guest.created_by, ...) avant de retourner quoi que ce soit — la
délégation n'excède jamais ce que son délégant peut lui-même lire."""

from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.db import get_session
from app.items import repository as items_repo
from app.sharing import repository as sharing_repo
from app.sharing.share_links import (
    ShareLinkTokenClaims,
    ShareLinkTokenError,
    decode_share_link_token,
)


@dataclass(frozen=True)
class GuestActor:
    tenant_id: str
    item_id: str
    share_link_id: str
    created_by: str
    allowed_item_ids: frozenset[str]
    allowed_collection_ids: frozenset[str]


def authorize_guest_item_read(guest: GuestActor | None, item_id: str) -> bool:
    return guest is not None and item_id in guest.allowed_item_ids


def authorize_guest_collection_read(guest: GuestActor | None, collection_id: str) -> bool:
    return guest is not None and collection_id in guest.allowed_collection_ids


def resolve_guest_scope(
    session: Session, claims: ShareLinkTokenClaims, *, created_by: str
) -> GuestActor | None:
    facts = items_repo.get_access_facts(session, tenant_id=claims.tenant_id, item_id=claims.item_id)
    if facts is None:
        return None
    root = configs_repo.get_config_by_item(session, claims.item_id)
    if root is None or root.kind not in ("app", "dashboard"):
        return None

    allowed_item_ids = {claims.item_id}
    allowed_collection_ids: set[str] = set()
    for ds in root.config.dataSources:
        if ds.type == "static":
            continue
        if ds.datasetId:
            # Cloisonnement tenant explicite : get_access_facts filtre déjà
            # par tenant_id (claims.tenant_id, jamais celui du dataset
            # référencé) — un datasetId pointant vers un item d'un autre
            # tenant ne matche aucune ligne et est silencieusement ignoré.
            ds_facts = items_repo.get_access_facts(
                session, tenant_id=claims.tenant_id, item_id=ds.datasetId
            )
            if ds_facts is None:
                continue
            allowed_item_ids.add(ds.datasetId)
            ds_config = configs_repo.get_config_by_item(session, ds.datasetId)
            if (
                ds_config is not None
                and ds_config.kind == "dataset"
                and ds_config.config.dataset is not None
                and ds_config.config.dataset.source == "collection"
                and ds_config.config.dataset.collectionId
            ):
                allowed_collection_ids.add(ds_config.config.dataset.collectionId)
        elif ds.layer:
            allowed_collection_ids.add(ds.layer)

    return GuestActor(
        tenant_id=claims.tenant_id,
        item_id=claims.item_id,
        share_link_id=claims.share_link_id,
        created_by=created_by,
        allowed_item_ids=frozenset(allowed_item_ids),
        allowed_collection_ids=frozenset(allowed_collection_ids),
    )


def get_share_link_actor(
    x_share_link_token: str | None = Header(default=None, alias="X-Share-Link-Token"),
    session: Session = Depends(get_session),
) -> GuestActor | None:
    """Dépendance FastAPI additive — ne lève jamais, quel que soit le jeton
    (absent, invalide, révoqué) : elle ne fait que produire (ou non) un
    GuestActor, elle ne décide d'aucun refus (les routes appelantes
    combinent ceci avec get_current_user optionnel + authorize_guest_*)."""
    if not x_share_link_token:
        return None
    try:
        claims = decode_share_link_token(x_share_link_token)
    except ShareLinkTokenError:
        return None
    link = sharing_repo.get_active_share_link(
        session, tenant_id=claims.tenant_id, link_id=claims.share_link_id
    )
    if link is None:
        return None
    return resolve_guest_scope(session, claims, created_by=link.created_by)
