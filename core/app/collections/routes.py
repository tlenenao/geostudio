# SPDX-License-Identifier: Apache-2.0
import logging
import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.attachments import repository as attachments_repo
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional, is_quotas_enabled
from app.collections import repository as repo
from app.collections.ddl import TenantColumnMismatch
from app.collections.introspection import (
    Introspector,
    TableNotFound,
    UnsupportedTable,
)
from app.collections.provisioning import create_empty_collection
from app.collections.publication import remove_table_from_publication
from app.collections.schema_json import table_info_to_schema
from app.collections.schemas import (
    AttachmentFieldSpec,
    CollectionCreate,
    CollectionPatch,
    EmptyCollectionCreate,
)
from app.configs import repository as configs_repo
from app.db import core_table_names, get_session
from app.quotas.service import check_quota_or_raise
from app.roles.guards import has_privilege, privilege_required_error, require_privilege
from app.roles.privileges import Privilege
from app.sharing.authorization import can
from app.sharing.schemas import Sharing

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

# Tables système PostGIS : de simples tables Postgres ordinaires (PK simple,
# pas de tenant_id) qui passeraient toutes les autres gardes. Les enregistrer
# comme collection ALTERerait une table système partagée par toute l'instance
# PostGIS (tenant_id, RLS, grants) — à exclure explicitement, la denylist
# core_table_names() ne les connaît pas (ce ne sont pas des modèles du cœur).
POSTGIS_SYSTEM_TABLES = frozenset(
    {
        "spatial_ref_sys",
        "geometry_columns",
        "geography_columns",
    }
)


def _core_tables() -> frozenset[str]:
    # Calculé à la requête, jamais à l'import : au moment où main.py importe ce
    # module, app.items/app.configs ne sont pas encore importés et
    # Base.metadata serait incomplet (denylist trouée).
    return core_table_names() | {"alembic_version"} | POSTGIS_SYSTEM_TABLES


def get_introspector() -> Introspector:  # overridé en test ; task 7 branche le vrai
    from app.collections.introspection_pg import introspect_table

    return introspect_table


def get_ddl_applier() -> Callable[[Session, str], None]:  # task 8 branche le vrai
    from app.collections.ddl import apply_collection_ddl

    return apply_collection_ddl


def get_table_lister() -> Callable[[Session], list[str]]:  # overridé en test
    from app.collections.introspection_pg import list_public_tables

    return list_public_tables


def get_s3_client():  # overridé dans main.py quand S3_* est configuré
    # Redéfini localement (comme app.attachments.routes.get_s3_client, cf.
    # commentaire pyproject.toml sur "app.attachments.routes ->
    # app.ingestion.storage") plutôt qu'importé depuis app.attachments —
    # app.attachments est AU-DESSUS d'app.collections dans le contrat de
    # couches, l'importer créerait une exemption de plus. Clé d'override
    # DISTINCTE de attachments_routes.get_s3_client (SP-42/
    # F-securite-tenant-rls-03) : unregister_collection en a besoin pour
    # purger les pièces jointes d'une collection avant sa suppression.
    raise RuntimeError("S3 client dependency not configured")


def get_attachments_bucket() -> str:
    # Duplique app.attachments.routes.get_attachments_bucket (même raison
    # que get_s3_client ci-dessus : éviter une exemption de couches pour un
    # simple accès à une variable d'environnement).
    return os.environ.get("S3_ATTACHMENTS_BUCKET", "geostudio-attachments")


def get_extent_provider():
    """Défaut : emprise réelle sous rls_scope. app.collections ne peut pas
    importer app.features (couche supérieure) — le scope RLS vit donc en
    double minimal ici : les deux SET sont inline (3 lignes), pas d'import."""
    from sqlalchemy import text as _text

    from app.collections.extent import table_extent

    def provider(session, info, tenant_id):
        if session.get_bind().dialect.name != "postgresql":
            return None
        session.execute(_text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id})
        session.execute(_text("SET LOCAL ROLE gis_rls"))
        try:
            return table_extent(session, info)
        finally:
            try:
                session.execute(_text("RESET ROLE"))
            except DBAPIError as exc:
                # Transaction avortée par l'échec de table_extent (25P02) : le
                # RESET échouerait et masquerait l'erreur d'origine ; le
                # rollback rend le rôle. Tout autre échec remonte (même
                # discipline que app/features/rls.py).
                if getattr(exc.orig, "sqlstate", None) != "25P02":
                    raise

    return provider


def get_feature_counter():
    """Défaut : COUNT(*) réel sur la table backing. None hors PostgreSQL
    (tests SQLite) : la collection reste avec feature_count=None, cohérent
    avec le comportement documenté pour les collections pré-SP-6c non
    encore backfillées. Pas de scope RLS ici (contrairement à
    get_extent_provider) : à l'enregistrement, on veut le compte physique
    total de la table, pas une vue filtrée par tenant — RLS ne s'applique
    de toute façon qu'après apply_ddl, déjà passé à ce stade."""
    from sqlalchemy import text as _text

    from app.sql_ident import quote_ident

    def counter(session, table_name):
        if session.get_bind().dialect.name != "postgresql":
            return None
        t = quote_ident(session, table_name)
        return session.execute(_text(f"SELECT count(*) FROM public.{t}")).scalar_one()

    return counter


def _collection_json(col, permissions, owner: str | None = None) -> dict:
    return {
        "id": col.id,
        "title": col.title,
        "description": col.description,
        "tableName": col.table_name,
        "isPublic": col.is_public,
        "editable": col.editable,
        "geometryType": col.geometry_type,
        "srid": col.srid,
        "pkColumn": col.pk_column,
        "permissions": permissions.model_dump(),
        "featureCount": col.feature_count,
        "owner": owner,
        "attachmentFields": col.attachment_fields,
        "license": col.license,
        "licenseUri": col.license_uri,
        "producer": col.producer,
        "contact": col.contact,
        "updateFrequency": col.update_frequency,
        "lineage": col.lineage,
        "language": col.language,
        "version": col.version,
        "temporalStart": col.temporal_start.isoformat() if col.temporal_start else None,
        "temporalEnd": col.temporal_end.isoformat() if col.temporal_end else None,
    }


def get_readable_collection(session, user, collection_id, *, can_manage_collections: bool = False):
    """404 avant 403 : une collection illisible est indistinguable d'une absente.

    `can_manage_collections` (privilège `admin.collections.manage`, SP-35) élargit
    la visibilité exactement comme `can_see_all` le fait déjà pour
    `list_visible_collections` : un rôle sur mesure porteur de ce privilège doit
    voir individuellement (GET/PATCH/DELETE) toute collection qu'il voit déjà en
    liste, pas seulement les siennes/partagées/publiques — sinon un même
    utilisateur verrait une collection dans `GET /collections` puis un 404 en
    cliquant dessus ou en la supprimant (piège n°5, chemin de lecture oublié,
    appliqué ici à la visibilité individuelle plutôt qu'au verdict `delete`)."""
    col = None
    if user is not None:
        col = repo.get_collection(session, tenant_id=user.tenant_id, collection_id=collection_id)
    else:
        from app.tenants.repository import get_or_create_default_tenant

        tenant = get_or_create_default_tenant(session)
        col = repo.get_collection(session, tenant_id=tenant.id, collection_id=collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="collection not found")
    readable = can_manage_collections or can(
        session,
        user_id=user.id if user else "",
        action="read",
        item=repo.get_access_facts(col),
        kind="collection",
        actor_is_admin=bool(user and user.is_admin),
    )
    if not readable:
        raise HTTPException(status_code=404, detail="collection not found")
    return col


@router.post("/collections", status_code=201)
def register_collection(
    body: CollectionCreate,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
    count_features=Depends(get_feature_counter),
):
    require_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    if body.tableName in _core_tables():
        raise HTTPException(status_code=400, detail="core table cannot be registered")
    if repo.get_collection(session, tenant_id=user.tenant_id, collection_id=body.tableName):
        raise HTTPException(status_code=409, detail="table already registered")
    # REV-011 : la vérification ci-dessus est tenant-scopée, donc aveugle à un
    # id (== nom de table) déjà pris par un AUTRE tenant — `Collection.id` est
    # une PK globale, distincte de la contrainte unique (tenant_id,
    # table_name). Sans cette seconde garde, l'INSERT plus bas percuterait
    # cette PK et lèverait une IntegrityError non rattrapée (500) au lieu d'un
    # 409 explicite.
    if repo.get_collection_by_id_any_tenant(session, collection_id=body.tableName) is not None:
        raise HTTPException(status_code=409, detail="table id already registered by another tenant")
    try:
        info = introspect(session, body.tableName)
    except TableNotFound as exc:
        raise HTTPException(status_code=400, detail="table not found in schema public") from exc
    except UnsupportedTable as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc
    try:
        apply_ddl(session, info.table_name, tenant_id=user.tenant_id)
    except TenantColumnMismatch as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    col = repo.create_collection(
        session,
        tenant_id=user.tenant_id,
        owner_id=user.id,
        table_name=info.table_name,
        title=body.title or info.table_name,
        description=body.description,
        is_public=body.isPublic,
        pk_column=info.pk_column,
        geometry_column=info.geometry_column,
        geometry_type=info.geometry_type,
        srid=info.srid,
        feature_count=count_features(session, info.table_name),
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="collection.create",
        object_type="collection",
        object_id=col.id,
        payload={"tableName": col.table_name},
    )
    # require_privilege() plus haut n'a pas levé : le privilège est donc déjà
    # prouvé pour cette requête, inutile de le requêter une seconde fois.
    can_manage_collections = True
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        can_manage_collections=can_manage_collections,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)


@router.post("/collections/empty", status_code=201)
def create_empty_collection_route(
    body: EmptyCollectionCreate,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
):
    # SP-42, correctif 1 (F-securite-autorisation-01) : cette route exécute du
    # DDL (création de table PostGIS) — réservée à data.manage (Créateur
    # l'a, Lecteur non), même privilège que POST /uploads.
    # ADMIN_COLLECTIONS_MANAGE a été explicitement écarté ici : l'assistant de
    # requête visuelle dépend de cette route pour tout utilisateur non-admin.
    require_privilege(session, user, Privilege.DATA_MANAGE.value)
    # SP-58 Tâche 5 (GAP-73/GAP-11) : même patron que create_config_service
    # (app.configs.service) — capacité éteinte par défaut, comportement
    # inchangé.
    if is_quotas_enabled():
        check_quota_or_raise(session, tenant_id=user.tenant_id, kind="collections")
    col = create_empty_collection(
        session,
        tenant_id=user.tenant_id,
        owner_id=user.id,
        title=body.title,
        columns=body.columns,
        geometry_type=body.geometryType,
        srid=body.srid,
        introspect=introspect,
        apply_ddl=apply_ddl,
    )
    can_manage_collections = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        can_manage_collections=can_manage_collections,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)


@router.get("/collections")
def list_collections(
    q: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.models import User

    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    can_manage_collections = bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )
    cols = repo.list_visible_collections(
        session,
        tenant_id=tenant_id,
        user_id=user.id if user else None,
        can_see_all=can_manage_collections,
        q=q,
    )
    limit = min(limit, MAX_LIMIT)
    total = len(cols)
    cols_page = cols[offset : offset + limit]
    owner_ids = {c.owner_id for c in cols_page}
    owners = (
        dict(session.execute(select(User.id, User.username).where(User.id.in_(owner_ids))).all())
        if owner_ids
        else {}
    )
    permissions_by_id = repo.collection_permissions_by_id(
        session,
        tenant_id=tenant_id,
        current_user_id=user.id if user else None,
        actor_is_admin=bool(user and user.is_admin),
        can_manage_collections=can_manage_collections,
        collections=cols_page,
    )
    return {
        "collections": [
            _collection_json(c, permissions_by_id[c.id], owner=owners.get(c.owner_id))
            for c in cols_page
        ],
        "numberMatched": total,
        "numberReturned": len(cols_page),
    }


@router.get("/collections/candidates")
def list_candidate_tables(
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
    list_tables: Callable[[Session], list[str]] = Depends(get_table_lister),
    introspect: Introspector = Depends(get_introspector),
):
    require_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    core = _core_tables()
    candidates = []
    for table_name in list_tables(session):
        if table_name in core:
            continue
        # REV-011 : exclusion cross-tenant (pas seulement tenant-scopée) —
        # une table déjà enregistrée par N'IMPORTE QUEL tenant percuterait la
        # même PK globale (`Collection.id`) qu'une table déjà enregistrée par
        # ce tenant-ci ; l'ancienne vérification tenant-scopée la laissait
        # apparaître comme "candidate" alors que l'enregistrer échouerait.
        if repo.get_collection_by_id_any_tenant(session, collection_id=table_name) is not None:
            continue
        try:
            info = introspect(session, table_name)
        except UnsupportedTable as exc:
            candidates.append({"tableName": table_name, "registrable": False, "reason": exc.reason})
            continue
        except TableNotFound:
            continue  # can't happen by construction: table_name came from list_tables itself
        candidates.append(
            {
                "tableName": table_name,
                "registrable": True,
                "geometryType": info.geometry_type,
                "srid": info.srid,
                "columnCount": len(info.columns),
            }
        )
    return {"candidates": candidates}


@router.get("/collections/{collection_id}")
def get_collection(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    extent_provider=Depends(get_extent_provider),
):
    can_manage_collections = bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )
    col = get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections
    )
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=col.tenant_id,
        current_user_id=user.id if user else None,
        actor_is_admin=bool(user and user.is_admin),
        can_manage_collections=can_manage_collections,
        collections=[col],
    )[col.id]
    body = _collection_json(col, permissions)
    body["itemType"] = "feature"
    # request.base_url ne porte jamais /v1 (juste scheme://host/) — ce
    # routeur est nesté sous /v1 (SP-57b), l'ajouter explicitement ici.
    base = str(request.base_url).rstrip("/") + "/v1"
    body["links"] = [
        {"rel": "self", "type": "application/json", "href": f"{base}/collections/{col.id}"},
        {
            "rel": "items",
            "type": "application/geo+json",
            "href": f"{base}/collections/{col.id}/items",
        },
    ]
    try:
        info = introspect(session, col.table_name)
        bbox = extent_provider(session, info, col.tenant_id)
    except (TableNotFound, UnsupportedTable, DBAPIError) as exc:
        # Table disparue/mutée ou erreur SQL : la description reste servie
        # sans extent ; un bug de code, lui, doit remonter (pas d'except large).
        logger.warning("extent lookup failed for collection %s: %s", col.id, exc)
        bbox = None
    body["extent"] = {"spatial": {"bbox": [bbox]}} if bbox else None
    return body


@router.get("/collections/{collection_id}/schema")
def get_collection_schema(
    collection_id: str,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
):
    can_manage_collections = bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )
    col = get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections
    )
    try:
        info = introspect(session, col.table_name)
    except TableNotFound as exc:
        raise HTTPException(status_code=404, detail="backing table not found") from exc
    except UnsupportedTable as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    return table_info_to_schema(info, attachment_fields=col.attachment_fields)


def _reject_attachment_field_collisions(
    session: Session,
    col,
    attachment_fields: list[AttachmentFieldSpec],
    introspect: Introspector,
) -> None:
    # SP-42/F-coeur-contenu-03 : AttachmentFieldSpec.key n'était validé ni
    # contre les colonnes SQL réelles ni (ici, côté DB) contre pk_column/
    # tenant_id/geometry_column — table_info_to_schema (schema_json.py)
    # concatène colonnes introspectées et attachmentFields sans
    # dédoublonnage, donc GET /collections/{id}/schema pouvait exposer deux
    # champs du même nom (l'un "string", l'autre "attachment"). Le
    # dédoublonnage ENTRE attachmentFields eux-mêmes est déjà couvert par
    # CollectionPatch._reject_duplicate_attachment_field_keys (schemas.py,
    # sans DB) ; ceci couvre la collision avec une colonne réelle, qui a
    # besoin de l'introspecteur.
    if not attachment_fields:
        return
    try:
        info = introspect(session, col.table_name)
    except (TableNotFound, UnsupportedTable):
        # Table backing disparue/mutée : rien à valider contre — même
        # discipline que get_extent_provider/get_collection_schema, qui ne
        # font pas planter la requête pour cette raison ailleurs dans ce
        # module. patch_collection continue normalement (l'écriture des
        # autres champs ne doit pas dépendre de la table backing).
        return
    reserved = {info.pk_column, "tenant_id", info.geometry_column} | {c.name for c in info.columns}
    collisions = sorted({spec.key for spec in attachment_fields if spec.key in reserved})
    if collisions:
        joined = ", ".join(collisions)
        raise HTTPException(
            status_code=422,
            detail=f"attachmentFields key(s) collide with an existing column: {joined}",
        )


@router.patch("/collections/{collection_id}")
def patch_collection(
    collection_id: str,
    body: CollectionPatch,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
):
    can_manage_collections = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    col = get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections
    )
    # can_manage_collections lève seulement le voile de visibilité ci-dessus, pas
    # ce garde d'écriture : un porteur non-propriétaire d'admin.collections.manage
    # qui arrive ici sans accès write réel (propriétaire/partage éditeur/rôle
    # admin) reçoit 403 (contre 404 avant get_readable_collection).
    if not can(
        session,
        user_id=user.id,
        action="write",
        item=repo.get_access_facts(col),
        kind="collection",
        actor_is_admin=user.is_admin,
    ):
        raise HTTPException(status_code=403, detail="write access required")
    if body.attachmentFields is not None:
        _reject_attachment_field_collisions(session, col, body.attachmentFields, introspect)
    text_changed = (body.title is not None and body.title != col.title) or (
        body.description is not None and body.description != col.description
    )
    for attr, value in (
        ("title", body.title),
        ("description", body.description),
        ("is_public", body.isPublic),
        ("editable", body.editable),
        ("license", body.license),
        ("license_uri", body.licenseUri),
        ("producer", body.producer),
        ("contact", body.contact),
        ("update_frequency", body.updateFrequency),
        ("lineage", body.lineage),
        ("language", body.language),
        ("version", body.version),
    ):
        if value is not None:
            setattr(col, attr, value)
    # temporalStart/temporalEnd sont typés date | None sans représentation
    # "vide" non-None distincte : la boucle générique ci-dessus ne peut pas
    # distinguer "champ omis" de "champ explicitement mis à null" (les deux
    # valent None côté Python). model_fields_set permet de savoir si la clé
    # était présente dans le JSON de la requête, même avec une valeur null,
    # ce qui permet d'effacer une emprise temporelle déjà déclarée (SP-41,
    # correctif de revue finale).
    if "temporalStart" in body.model_fields_set:
        col.temporal_start = body.temporalStart
    if "temporalEnd" in body.model_fields_set:
        col.temporal_end = body.temporalEnd
    if body.attachmentFields is not None:
        col.attachment_fields = [f.model_dump() for f in body.attachmentFields]
    session.flush()
    if text_changed:
        repo.enqueue_embedding(col.id, user.tenant_id)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="collection.update",
        object_type="collection",
        object_id=col.id,
        payload=body.model_dump(exclude_none=True, mode="json"),
    )
    permissions = repo.collection_permissions_by_id(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        actor_is_admin=user.is_admin,
        can_manage_collections=can_manage_collections,
        collections=[col],
    )[col.id]
    return _collection_json(col, permissions)


@router.delete("/collections/{collection_id}", status_code=204)
def unregister_collection(
    collection_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
):
    can_manage_collections = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    col = get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections
    )
    # après le 404 : un non-admin qui la voit reçoit 403. can_manage_collections
    # est déjà le résultat de ce même privilège (calculé ci-dessus) : pas besoin
    # de le requêter une seconde fois via require_privilege().
    if not can_manage_collections:
        raise privilege_required_error(Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    # SP-42/F-coeur-contenu-04 : sans cette garde, supprimer une collection
    # encore référencée par un Dataset (via dataset.collectionId) laissait ce
    # Dataset orphelin silencieusement (204, aucun signal). Avant toute
    # opération destructive (dépublication, purge des pièces jointes,
    # suppression) : aucun effet de bord tant qu'une référence existe.
    referencing = configs_repo.find_referencing_config_kinds(
        session, tenant_id=col.tenant_id, collection_id=col.id
    )
    if referencing:
        raise HTTPException(
            status_code=409,
            detail=f"still referenced by config kind(s): {', '.join(referencing)}",
        )
    remove_table_from_publication(session, col.table_name)
    # SP-42/F-securite-tenant-rls-03 : sans cette purge explicite (lignes +
    # objets S3), repo.delete_collection plantait en 500 (IntegrityError) dès
    # qu'une pièce jointe existait sur une entité de la collection — la FK
    # attachments.collection_id n'avait ondelete="CASCADE" que depuis la
    # migration 0034, qui n'aurait supprimé que la ligne, jamais l'objet S3.
    attachments_repo.delete_all_for_collection(
        session,
        s3,
        get_attachments_bucket(),
        tenant_id=col.tenant_id,
        collection_id=col.id,
    )
    repo.delete_collection(session, col)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="collection.delete",
        object_type="collection",
        object_id=collection_id,
        payload={},
    )


def _require_share(session, user, col) -> None:
    if not can(
        session,
        user_id=user.id,
        action="share",
        item=repo.get_access_facts(col),
        kind="collection",
        actor_is_admin=user.is_admin,
    ):
        raise HTTPException(status_code=403, detail="share access required")


@router.get("/collections/{collection_id}/sharing", response_model=Sharing)
def get_sharing(
    collection_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    can_manage_collections = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    col = get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections
    )
    _require_share(session, user, col)
    shares = repo.get_collection_sharing(session, tenant_id=user.tenant_id, collection_id=col.id)
    return {
        "public": col.is_public,
        "groups": [{"groupId": s.group_id, "role": s.role} for s in shares],
    }


@router.put("/collections/{collection_id}/sharing", response_model=Sharing)
def put_sharing(
    collection_id: str,
    body: Sharing,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    can_manage_collections = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    col = get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections
    )
    _require_share(session, user, col)
    ok = repo.set_collection_sharing(
        session,
        tenant_id=user.tenant_id,
        collection_id=col.id,
        groups=[(g.groupId, g.role) for g in body.groups],
    )
    if not ok:
        # Même statut/détail que le chemin items (items/routes.py) : ne jamais
        # révéler l'existence d'un groupe d'un autre tenant. is_public n'est
        # muté qu'après validation — rien n'a changé à ce stade.
        raise HTTPException(status_code=404, detail="group not found")
    col.is_public = body.public
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="collection.share",
        object_type="collection",
        object_id=col.id,
        payload={"public": body.public, "groups": [g.model_dump() for g in body.groups]},
    )
    return {
        "public": col.is_public,
        "groups": [{"groupId": g.groupId, "role": g.role} for g in body.groups],
    }
