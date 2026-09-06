# SPDX-License-Identifier: Apache-2.0
"""Provisionne une collection vide (schéma explicite, aucune ligne) pour un
consommateur qui la remplira lui-même ensuite — premier appelant : l'assistant
de requête visuelle (SP-14o), qui a besoin d'une collection de sortie avant de
pouvoir sauvegarder le pipeline qui l'alimentera. Factorise le motif
CREATE TABLE + apply_collection_ddl + create_collection déjà écrit dans
app.ingestion.importer.run_import (SP-6a), sans insertion de lignes et avec
geometry_type/srid nullables (l'ingestion importe toujours un fichier
géoréférencé ; le cas non-spatial ne lui a jamais été nécessaire)."""

import uuid
from collections.abc import Callable
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.collections import repository as collections_repo
from app.collections.introspection import Introspector
from app.collections.models import Collection
from app.collections.schemas import EmptyCollectionColumn
from app.sql_ident import quote_ident


def create_empty_collection(
    session: Session,
    *,
    tenant_id: str,
    owner_id: str,
    title: str,
    columns: list[EmptyCollectionColumn],
    geometry_type: Literal[
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    ]
    | None,
    srid: int | None,
    introspect: Introspector,
    apply_ddl: Callable[[Session, str], None],
) -> Collection:
    table_name = f"query_{uuid.uuid4().hex[:12]}"
    t = quote_ident(session, table_name)
    col_defs = ", ".join(f"{quote_ident(session, c.name)} {c.sqlType}" for c in columns)
    create_sql = f"CREATE TABLE public.{t} (id serial PRIMARY KEY, tenant_id text NOT NULL"
    if col_defs:
        create_sql += f", {col_defs}"
    if geometry_type is not None:
        create_sql += f", geom geometry({geometry_type}, {srid or 4326})"
    create_sql += ")"
    session.execute(text(create_sql))

    info = introspect(session, table_name)
    apply_ddl(session, table_name)
    col = collections_repo.create_collection(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        table_name=table_name,
        title=title,
        description="",
        is_public=False,
        pk_column=info.pk_column,
        geometry_column=info.geometry_column,
        geometry_type=info.geometry_type,
        srid=info.srid,
        feature_count=0,
    )
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=owner_id,
        actor_kind="user",
        action="collection.create",
        object_type="collection",
        object_id=col.id,
        payload={"tableName": col.table_name},
    )
    return col
