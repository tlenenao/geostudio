# SPDX-License-Identifier: Apache-2.0
"""Limites géographiques de lecture/écriture (GAP-27, REV-121).

Spec : docs/superpowers/specs/2026-10-10-sp-geo-limits-design.md.

Ce module ne DÉCIDE pas de l'accès à une collection (c'est `can()`/`decide()`,
`app.sharing.authorization`) : il résout, pour un utilisateur, les géométries
qui RÉTRÉCISSENT l'ensemble de lignes qu'il voit, et pose le GUC transactionnel
`app.geo_limits` que la policy RLS restrictive par collection
(`app.collections.ddl.ensure_geo_limit_policy`) consomme. Les chemins de lecture
qui ne passent pas par Postgres (lac DuckDB, pièces jointes, export d'app) ne
peuvent pas appliquer la policy : ils appellent `refuse_if_geo_limited`
(fail-closed)."""

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi import HTTPException
from shapely.geometry import shape
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.sharing.models import CollectionGeoLimit, GroupMember
from app.users.models import User

TARGET_TYPES = ("role", "group")
MAX_VERTICES = 5_000  # borne de coût de la policy (spec §8)

# table_name -> géométries GeoJSON applicables ; liste vide = ne voit rien.
GeoLimits = Mapping[str, list[dict]]


class InvalidGeoLimit(ValueError):
    """Géométrie de limite refusée (→ 422)."""


class GeoLimitRefused(HTTPException):
    """Chemin de lecture qui ne sait pas appliquer une limite : refus (fail-closed)."""

    def __init__(self, path: str = "this read path"):
        super().__init__(
            status_code=403,
            detail=f"geo_limit_unsupported: {path} is not available on a geo-limited collection",
        )


def _vertex_count(geom) -> int:
    from shapely import get_num_coordinates

    return int(get_num_coordinates(geom))


def validate_limit_geometry(geometry: object) -> dict:
    """GeoJSON Polygon/MultiPolygon WGS84, non vide, valide, borné. Renvoie la
    géométrie normalisée (dict JSON) ; lève InvalidGeoLimit sinon."""
    if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise InvalidGeoLimit("geometry must be a GeoJSON Polygon or MultiPolygon")
    try:
        geom = shape(geometry)
    except Exception as exc:  # noqa: BLE001 - shapely lève des types variés sur un GeoJSON invalide
        raise InvalidGeoLimit("geometry is not valid GeoJSON") from exc
    if geom.is_empty:
        raise InvalidGeoLimit("geometry must not be empty")
    minx, miny, maxx, maxy = geom.bounds
    if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
        raise InvalidGeoLimit("coordinates must be WGS84 (lon -180..180, lat -90..90)")
    if not geom.is_valid:
        raise InvalidGeoLimit("geometry is not a valid polygon (self-intersection?)")
    if _vertex_count(geom) > MAX_VERTICES:
        raise InvalidGeoLimit(f"geometry has more than {MAX_VERTICES} vertices")
    return {"type": geometry["type"], "coordinates": geometry["coordinates"]}


def _as_dict(value) -> dict:
    return json.loads(value) if isinstance(value, str) else value


def resolve_geo_limits(
    session: Session, *, tenant_id: str | None, user_id: str | None
) -> dict[str, list[dict]]:
    """Limites effectives par table. `user_id` None = anonyme : toute collection
    portant au moins une entrée (tous tenants) devient invisible (liste vide) —
    sans cela un utilisateur limité n'aurait qu'à se déconnecter pour lire une
    collection publique. Utilisateur : union des entrées dont la cible est son
    rôle ou l'un de ses groupes ; aucune entrée applicable = non limité."""
    if user_id is None:
        rows = session.execute(
            text(
                "SELECT DISTINCT c.table_name FROM collection_geo_limits g "
                "JOIN collections c ON c.id = g.collection_id"
            )
        ).all()
        return {r[0]: [] for r in rows}
    role_id = session.execute(select(User.role_id).where(User.id == user_id)).scalar()
    group_ids = list(
        session.execute(
            select(GroupMember.group_id).where(GroupMember.user_id == user_id)
        ).scalars()
    )
    principals = [("group", gid) for gid in group_ids]
    if role_id:
        principals.append(("role", role_id))
    if not principals:
        return {}
    limits: dict[str, list[dict]] = {}
    rows = session.execute(
        text(
            "SELECT c.table_name, g.target_type, g.target_id, g.geometry "
            "FROM collection_geo_limits g JOIN collections c ON c.id = g.collection_id "
            "WHERE g.tenant_id = :t"
        ),
        {"t": tenant_id},
    ).all()
    wanted = set(principals)
    for table_name, target_type, target_id, geometry in rows:
        if (target_type, target_id) in wanted:
            limits.setdefault(table_name, []).append(_as_dict(geometry))
    return limits


def set_geo_limits_guc(session: Session, limits: GeoLimits | None) -> None:
    """Pose app.geo_limits (transaction-locale, paramétrée comme app.tenant_id).
    Toujours posée, y compris `{}` : jamais de valeur périmée d'un scope voisin."""
    payload = json.dumps(dict(limits or {}), separators=(",", ":"))
    session.execute(text("SELECT set_config('app.geo_limits', :v, true)"), {"v": payload})


def refuse_if_geo_limited(
    limits: GeoLimits | None, table_name: str, *, path: str = "this read path"
) -> None:
    if limits and table_name in limits:
        raise GeoLimitRefused(path)


def refuse_if_collection_has_limits(
    session: Session, *, tenant_id: str, collection_id: str, path: str
) -> None:
    """Export distribué hors du cœur, sans identité de lecteur : aucune limite ne
    peut s'y appliquer — toute collection portant au moins une entrée est refusée."""
    if list_limits(session, tenant_id=tenant_id, collection_id=collection_id):
        raise GeoLimitRefused(path)


# --- CRUD (routes d'administration) -----------------------------------------


def list_limits(session: Session, *, tenant_id: str, collection_id: str):
    return list(
        session.execute(
            select(CollectionGeoLimit)
            .where(
                CollectionGeoLimit.tenant_id == tenant_id,
                CollectionGeoLimit.collection_id == collection_id,
            )
            .order_by(CollectionGeoLimit.target_type, CollectionGeoLimit.target_id)
        ).scalars()
    )


def get_limit(
    session: Session, *, tenant_id: str, collection_id: str, target_type: str, target_id: str
) -> CollectionGeoLimit | None:
    return session.execute(
        select(CollectionGeoLimit).where(
            CollectionGeoLimit.tenant_id == tenant_id,
            CollectionGeoLimit.collection_id == collection_id,
            CollectionGeoLimit.target_type == target_type,
            CollectionGeoLimit.target_id == target_id,
        )
    ).scalar_one_or_none()


def upsert_limit(
    session: Session,
    *,
    tenant_id: str,
    collection_id: str,
    target_type: str,
    target_id: str,
    geometry: dict,
    actor_id: str,
) -> CollectionGeoLimit:
    row = get_limit(
        session,
        tenant_id=tenant_id,
        collection_id=collection_id,
        target_type=target_type,
        target_id=target_id,
    )
    if row is None:
        row = CollectionGeoLimit(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            collection_id=collection_id,
            target_type=target_type,
            target_id=target_id,
            geometry=geometry,
            created_by=actor_id,
        )
        session.add(row)
    else:
        row.geometry = geometry
        row.updated_at = datetime.now(UTC)
    session.flush()
    return row


def delete_limit(
    session: Session, *, tenant_id: str, collection_id: str, target_type: str, target_id: str
) -> bool:
    result = session.execute(
        delete(CollectionGeoLimit).where(
            CollectionGeoLimit.tenant_id == tenant_id,
            CollectionGeoLimit.collection_id == collection_id,
            CollectionGeoLimit.target_type == target_type,
            CollectionGeoLimit.target_id == target_id,
        )
    )
    return result.rowcount == 1
