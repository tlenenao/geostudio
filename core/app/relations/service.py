# SPDX-License-Identifier: Apache-2.0
"""Relations entre collections (ARC-21, ADR 0021) : déclaration, enregistrements liés,
garde de suppression (restrict/cascade) et de clé étrangère logique à l'écriture.

Règle de lecture : tout enregistrement lié est lu SOUS la RLS (tenant, limite
géographique) et le masquage de SA collection — jamais au rang propriétaire. Les
vérifications d'intégrité (restrict, 1-1) comptent au rang propriétaire (tenant
explicite) : un enfant invisible de l'appelant bloque quand même la suppression."""

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.attachments import repository as attachments_repo
from app.audit.writer import write_audit
from app.collections import repository as collections_repo
from app.collections.introspection import hide_sensitive_columns
from app.collections.introspection_pg import introspect_table
from app.collections.models import Collection
from app.collections.routes import get_readable_collection
from app.collections.sensitive import may_read_sensitive
from app.errors import ValidationHTTPException
from app.features import repository as features_repo
from app.history import service as history
from app.relations.models import CollectionRelation
from app.sharing.authorization import can
from app.sql_ident import quote_ident

MAX_DEPTH = 5  # profondeur de cascade ; au-delà : 409 (cycle ou chaîne démesurée)
MAX_LINKED = 1000  # enregistrements liés lus / supprimés en une fois
MAX_PAGE = 200


# --- accès aux collections -------------------------------------------------------


def writable_collection(session: Session, user, collection_id: str) -> Collection:
    """Même verdict que `_get_writable` (features) : 404 avant 403, `can()` write."""
    col = get_readable_collection(session, user, collection_id)
    if not can(
        session,
        user_id=user.id,
        action="write",
        item=collections_repo.get_access_facts(col),
        kind="collection",
        actor_is_admin=user.acts_as_admin(),
    ):
        raise HTTPException(status_code=403, detail="write access required")
    return col


def _same_tenant_collection(session: Session, tenant_id: str, collection_id: str) -> Collection:
    col = collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return col


# --- CRUD ----------------------------------------------------------------------------


def relations_of(session: Session, tenant_id: str, collection_id: str) -> list[CollectionRelation]:
    return list(
        session.scalars(
            select(CollectionRelation)
            .where(
                CollectionRelation.tenant_id == tenant_id,
                (CollectionRelation.parent_collection_id == collection_id)
                | (CollectionRelation.child_collection_id == collection_id)
                | (CollectionRelation.link_collection_id == collection_id),
            )
            .order_by(CollectionRelation.name)
        )
    )


def get_relation(session: Session, tenant_id: str, relation_id: str) -> CollectionRelation | None:
    return session.scalar(
        select(CollectionRelation).where(
            CollectionRelation.id == relation_id, CollectionRelation.tenant_id == tenant_id
        )
    )


def _invalid(field: str, code: str, message: str):
    return ValidationHTTPException(
        errors=[{"field": field, "code": code, "message": message}], status_code=422
    )


def _check_key(info, col: Collection, key: str, field: str, *, allow_pk: bool) -> None:
    names = {c.name for c in info.columns if c.name not in ("tenant_id", info.geometry_column)}
    if key not in names or (key == info.pk_column and not allow_pk):
        raise _invalid(field, "unknown_key", f"'{key}' is not a usable column of {col.id}")
    if key in col.sensitive_fields:
        raise _invalid(field, "sensitive_key", f"'{key}' is a sensitive field of {col.id}")


def create_relation(session: Session, user, body) -> CollectionRelation:
    """Déclare une relation. `can()` write sur CHAQUE collection concernée (ADR 0021),
    même tenant obligatoire (une collection d'un autre tenant est introuvable)."""
    parent = writable_collection(session, user, body.parentCollectionId)
    child = writable_collection(session, user, body.childCollectionId)
    link = None
    if body.cardinality == "many_to_many":
        if not (body.linkCollectionId and body.linkParentKey and body.linkChildKey):
            raise _invalid(
                "linkCollectionId", "link_required", "many_to_many needs a link collection"
            )
        link = writable_collection(session, user, body.linkCollectionId)
    elif body.linkCollectionId or body.linkParentKey or body.linkChildKey:
        raise _invalid("linkCollectionId", "link_forbidden", "only many_to_many uses a link")
    if any(c.tenant_id != user.tenant_id for c in (parent, child, link) if c is not None):
        raise HTTPException(status_code=404, detail="collection not found")  # pragma: no cover
    p_info = introspect_table(session, parent.table_name)
    c_info = introspect_table(session, child.table_name)
    parent_key = body.parentKey or p_info.pk_column
    _check_key(p_info, parent, parent_key, "parentKey", allow_pk=True)
    if body.cardinality == "many_to_many":
        child_key = body.childKey or c_info.pk_column
        _check_key(c_info, child, child_key, "childKey", allow_pk=True)
        l_info = introspect_table(session, link.table_name)  # type: ignore[union-attr]
        _check_key(l_info, link, body.linkParentKey, "linkParentKey", allow_pk=False)  # type: ignore[arg-type]
        _check_key(l_info, link, body.linkChildKey, "linkChildKey", allow_pk=False)  # type: ignore[arg-type]
    else:
        if not body.childKey:
            raise _invalid("childKey", "key_required", "childKey (foreign key column) is required")
        child_key = body.childKey
        _check_key(c_info, child, child_key, "childKey", allow_pk=False)
    dup = session.scalar(
        select(CollectionRelation.id).where(
            CollectionRelation.parent_collection_id == parent.id,
            CollectionRelation.name == body.name,
        )
    )
    if dup:
        raise HTTPException(status_code=409, detail="a relation with this name already exists")
    rel = CollectionRelation(
        tenant_id=user.tenant_id,
        name=body.name,
        cardinality=body.cardinality,
        parent_collection_id=parent.id,
        child_collection_id=child.id,
        parent_key=parent_key,
        child_key=child_key,
        link_collection_id=link.id if link else None,
        link_parent_key=body.linkParentKey,
        link_child_key=body.linkChildKey,
        on_delete=body.onDelete,
        created_by=user.id,
    )
    session.add(rel)
    session.flush()
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="relation.create",
        object_type="relation",
        object_id=rel.id,
        payload={
            "name": rel.name,
            "parent": parent.id,
            "child": child.id,
            "onDelete": rel.on_delete,
        },
    )
    return rel


def delete_relation(session: Session, user, rel: CollectionRelation) -> None:
    for cid in {rel.parent_collection_id, rel.child_collection_id, rel.link_collection_id} - {None}:
        writable_collection(session, user, cid)  # type: ignore[arg-type]
    session.delete(rel)
    session.flush()
    write_audit(
        session,
        tenant_id=rel.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="relation.delete",
        object_type="relation",
        object_id=rel.id,
        payload={"name": rel.name},
    )


# --- lecture des enregistrements liés --------------------------------------------


def _fid_text_filter(values: list) -> str:
    return ",".join(str(v).replace("\\", "\\\\").replace(",", "\\,") for v in values)


def _read_ctx(session: Session, user, col: Collection, rls):
    """(info masquée si besoin, masked, scope) pour lire `col` sous SES droits."""
    masked = not may_read_sensitive(session, user, col)
    info = introspect_table(session, col.table_name)
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    return info, masked


def _matching(session, user, col, key, values, *, limit, offset, rls):
    """Enregistrements de `col` dont `key` ∈ values, sous RLS + masquage de `col`.
    Renvoie (features, total) ; `total` ne compte QUE les lignes lisibles par l'appelant
    (AUD-163 : plus de fuite du nombre de valeurs liées masquées par la RLS)."""
    if not values:
        return [], 0
    info, masked = _read_ctx(session, user, col, rls)
    with rls(session, col.tenant_id, masked=masked):
        if key == info.pk_column:
            # la PK n'est pas filtrable côté repository : lecture unitaire de la page
            feats = []
            for v in values[offset : offset + limit]:
                f = features_repo.get_feature(session, info, fid=str(v))
                if f is not None:
                    feats.append(f)
            # total sous RLS : comptage SQL (la policy du rôle de scope filtre les lignes)
            coerced = [
                c for v in values if (c := features_repo._coerce_fid(info, str(v))) is not None
            ]
            q = lambda n: quote_ident(session, n)  # noqa: E731
            total = session.execute(
                text(
                    f"SELECT count(*) FROM public.{q(info.table_name)} "
                    f"WHERE {q(info.pk_column)} = ANY(:v)"
                ),
                {"v": coerced},
            ).scalar_one()
            return feats, total
        try:
            page = features_repo.select_features(
                session,
                info,
                limit=limit,
                offset=offset,
                filters={f"{key}__in": _fid_text_filter(values)},
                count_mode="exact",
            )
        except features_repo.FilterError as exc:
            # AUD-164 : une clé devenue inutilisable (colonne supprimée/sensible) = 422, pas 500.
            raise _invalid(exc.field or key, exc.code, exc.message) from exc
        return page.features, page.number_matched


def _source_value(feature: dict, info, key: str):
    if key == info.pk_column:
        return feature["id"]
    return (feature.get("properties") or {}).get(key)


def related_records(
    session: Session,
    user,
    rel: CollectionRelation,
    source_col: Collection,
    fid: str,
    *,
    direction: str | None,
    limit: int,
    offset: int,
    rls,
):
    """Enregistrements liés à (source_col, fid) selon `rel`. Les deux côtés (et la
    collection d'association) doivent être lisibles par l'appelant, sinon 404 : un
    enfant illisible n'existe pas pour lui."""
    limit = max(1, min(limit, MAX_PAGE))
    if direction is None:
        direction = "children" if source_col.id == rel.parent_collection_id else "parents"
    if direction not in ("children", "parents"):
        raise _invalid("direction", "invalid_direction", "direction must be children or parents")
    src_id = rel.parent_collection_id if direction == "children" else rel.child_collection_id
    dst_id = rel.child_collection_id if direction == "children" else rel.parent_collection_id
    if source_col.id != src_id:
        raise HTTPException(status_code=404, detail="relation not found")
    dst_col = get_readable_collection(session, user, dst_id)  # 404 si illisible
    link_col = (
        get_readable_collection(session, user, rel.link_collection_id)
        if rel.link_collection_id
        else None
    )
    src_key, dst_key = (
        (rel.parent_key, rel.child_key)
        if direction == "children"
        else (rel.child_key, rel.parent_key)
    )
    src_info, src_masked = _read_ctx(session, user, source_col, rls)
    with rls(session, source_col.tenant_id, masked=src_masked):
        feature = features_repo.get_feature(session, src_info, fid=fid)
    if feature is None:
        raise HTTPException(status_code=404, detail="feature not found")
    value = _source_value(feature, src_info, src_key)
    values: list = []
    if value is not None:
        if rel.cardinality != "many_to_many":
            values = [value]
        else:
            lk_in, lk_out = (
                (rel.link_parent_key, rel.link_child_key)
                if direction == "children"
                else (rel.link_child_key, rel.link_parent_key)
            )
            l_info, l_masked = _read_ctx(session, user, link_col, rls)  # type: ignore[arg-type]
            with rls(session, link_col.tenant_id, masked=l_masked):  # type: ignore[union-attr]
                try:
                    page = features_repo.select_features(
                        session,
                        l_info,
                        limit=MAX_LINKED,
                        offset=0,
                        filters={lk_in: str(value)},
                        count_mode="none",
                    )
                except features_repo.FilterError as exc:  # AUD-164
                    raise _invalid(exc.field or lk_in, exc.code, exc.message) from exc
            values = [
                p
                for f in page.features
                if (p := (f.get("properties") or {}).get(lk_out)) is not None
            ]
    feats, total = _matching(
        session, user, dst_col, dst_key, values, limit=limit, offset=offset, rls=rls
    )
    return direction, dst_col, feats, total


# --- intégrité à l'écriture --------------------------------------------------------


def _owner_values(session, col: Collection, info, key: str, in_key: str, value, *, cap: int):
    """Valeurs de `key` des lignes de `col` dont `in_key` = value (rang propriétaire,
    tenant explicite)."""
    q = lambda n: quote_ident(session, n)  # noqa: E731
    rows = session.execute(
        text(
            f"SELECT {q(key)} FROM public.{q(info.table_name)} "
            f"WHERE {q(in_key)} = :v AND tenant_id = :t LIMIT :cap"
        ),
        {"v": value, "t": col.tenant_id, "cap": cap},
    ).all()
    return [r[0] for r in rows]


def _key_value(session, col: Collection, info, key: str, fid: str):
    if key == info.pk_column:
        return features_repo._coerce_fid(info, fid)
    q = lambda n: quote_ident(session, n)  # noqa: E731
    value = features_repo._coerce_fid(info, fid)
    if value is None:
        return None
    row = session.execute(
        text(
            f"SELECT {q(key)} FROM public.{q(info.table_name)} "
            f"WHERE {q(info.pk_column)} = :f AND tenant_id = :t"
        ),
        {"f": value, "t": col.tenant_id},
    ).first()
    return row[0] if row else None


def check_write(session: Session, user, col: Collection, properties: dict, fid: str | None, rls):
    """Clé étrangère logique (ADR 0021) : pour chaque relation 1-1/1-N dont `col` est
    l'enfant, une valeur non nulle de `child_key` doit désigner un parent LISIBLE par
    l'appelant (RLS + limite géographique) ; 1-1 : un seul enfant par parent."""
    for rel in relations_of(session, col.tenant_id, col.id):
        if rel.child_collection_id != col.id or rel.cardinality == "many_to_many":
            continue
        value = (properties or {}).get(rel.child_key)
        if value is None:
            continue
        parent = get_readable_collection(session, user, rel.parent_collection_id)
        found, _total = _matching(
            session, user, parent, rel.parent_key, [value], limit=1, offset=0, rls=rls
        )
        if not found:
            raise ValidationHTTPException(
                errors=[
                    {
                        "field": rel.child_key,
                        "code": "relation_target_missing",
                        "message": f"no '{parent.id}' record with {rel.parent_key}={value}",
                    }
                ],
                status_code=422,
            )
        if rel.cardinality == "one_to_one":
            info = introspect_table(session, col.table_name)
            taken = _owner_values(session, col, info, info.pk_column, rel.child_key, value, cap=2)
            fid_val = features_repo._coerce_fid(info, fid) if fid is not None else None
            if any(t != fid_val for t in taken):
                raise HTTPException(
                    status_code=409,
                    detail=f"one_to_one relation '{rel.name}': parent already linked",
                )


def _existing_parent_values(session, user, parent: Collection, key: str, values: list, rls) -> set:
    """Valeurs de `key` parmi `values` qui désignent un parent LISIBLE (RLS + limite
    géographique), sous forme de chaînes. Une requête par tranche (clé non-PK)."""
    info, _masked = _read_ctx(session, user, parent, rls)
    if key == info.pk_column:  # ponytail: lecture unitaire (PK non filtrable), tranche à venir
        return {
            str(v)
            for v in values
            if _matching(session, user, parent, key, [v], limit=1, offset=0, rls=rls)[0]
        }
    found: set = set()
    for i in range(0, len(values), 200):
        chunk = values[i : i + 200]
        feats, _total = _matching(
            session, user, parent, key, chunk, limit=len(chunk), offset=0, rls=rls
        )
        found |= {str(_source_value(f, info, key)) for f in feats}
    return found


def check_rows(
    session: Session, user, col: Collection, rows: list[dict], rls, *, new_rows: bool
) -> dict[int, dict]:
    """Version GROUPÉE de `check_write` (AUD-165) pour les producteurs en masse (import,
    `writer.collection`, soumission approuvée) : même règle de clé étrangère logique, une
    lecture par tranche de valeurs distinctes. Renvoie {indice de ligne: erreur} (`code`,
    `field`, `message`, `status`) sans rien lever : l'appelant rejette la ligne selon sa
    politique. 1-1 : doublon DANS le lot toujours détecté ; doublon contre l'existant
    seulement pour des lignes neuves (`new_rows`), un upsert se réécrivant lui-même."""
    out: dict[int, dict] = {}
    for rel in relations_of(session, col.tenant_id, col.id):
        if rel.child_collection_id != col.id or rel.cardinality == "many_to_many":
            continue
        by_value: dict[str, list[int]] = {}
        originals: dict[str, object] = {}
        for i, props in enumerate(rows):
            v = (props or {}).get(rel.child_key)
            if v is not None:
                by_value.setdefault(str(v), []).append(i)
                originals.setdefault(str(v), v)
        if not by_value:
            continue
        parent = get_readable_collection(session, user, rel.parent_collection_id)
        found = _existing_parent_values(
            session, user, parent, rel.parent_key, list(originals.values()), rls
        )
        for sval, idxs in by_value.items():
            if sval not in found:
                for i in idxs:
                    out.setdefault(
                        i,
                        {
                            "field": rel.child_key,
                            "code": "relation_target_missing",
                            "message": f"no '{parent.id}' record with {rel.parent_key}={sval}",
                            "status": 422,
                        },
                    )
        if rel.cardinality != "one_to_one":
            continue
        taken: set = set()
        if new_rows:
            info = introspect_table(session, col.table_name)
            q = lambda n: quote_ident(session, n)  # noqa: E731
            vals = list(originals.values())
            for i in range(0, len(vals), 500):
                rows_db = session.execute(
                    text(
                        f"SELECT {q(rel.child_key)} FROM public.{q(info.table_name)} "
                        f"WHERE tenant_id = :t AND {q(rel.child_key)} = ANY(:v)"
                    ),
                    {"t": col.tenant_id, "v": vals[i : i + 500]},
                ).all()
                taken |= {str(r[0]) for r in rows_db}
        for sval, idxs in by_value.items():
            dup = idxs[1:] if sval not in taken else idxs
            for i in dup:
                out.setdefault(
                    i,
                    {
                        "field": rel.child_key,
                        "code": "relation_one_to_one",
                        "message": f"one_to_one relation '{rel.name}': parent already linked",
                        "status": 409,
                    },
                )
    return out


def parent_key_blocker(
    session: Session, col: Collection, parent_rels: list, old_props: dict, new_props: dict
) -> str | None:
    """Nom de la relation que le changement de `parent_key` (ancien -> nouveau) orphelinerait
    (enfants existants, rang propriétaire), sinon None. Version en masse de `before_update` :
    ne cascade jamais, `parent_rels` = relations dont `col` est le parent (lues une fois)."""
    for rel in parent_rels:
        key = rel.parent_key
        if key not in new_props:
            continue
        old, new = old_props.get(key), new_props[key]
        if old is None or str(old) == str(new):
            continue
        if rel.cardinality == "many_to_many":
            target_id, lk = rel.link_collection_id, rel.link_parent_key
        else:
            target_id, lk = rel.child_collection_id, rel.child_key
        target = _same_tenant_collection(session, col.tenant_id, target_id)  # type: ignore[arg-type]
        t_info = introspect_table(session, target.table_name)
        if _owner_values(session, target, t_info, t_info.pk_column, lk, old, cap=1):  # type: ignore[arg-type]
            return rel.name
    return None


def before_update(session: Session, user, col: Collection, fid: str, properties: dict, rls) -> None:
    """AUD-166 : un changement de `parent_key` d'un parent détacherait ses enfants. restrict
    (défaut) : 409 si des enregistrements liés existent (rang propriétaire). cascade : la
    nouvelle valeur est propagée à chaque enfant par la voie normale (can() write, RLS,
    journal ARC-15, audit), profondeur 1 ; une clé vidée (NULL) n'est jamais propagée."""
    rels = [
        r for r in relations_of(session, col.tenant_id, col.id) if col.id == r.parent_collection_id
    ]
    if not rels:  # chemin chaud
        return
    info = introspect_table(session, col.table_name)
    for rel in rels:
        key = rel.parent_key
        if key == info.pk_column:
            continue  # la PK ne se modifie pas
        old = _key_value(session, col, info, key, fid)
        new = (properties or {}).get(key)
        if old is None or (new is not None and str(new) == str(old)):
            continue
        if rel.cardinality == "many_to_many":
            target_id, lk = rel.link_collection_id, rel.link_parent_key
        else:
            target_id, lk = rel.child_collection_id, rel.child_key
        target = _same_tenant_collection(session, col.tenant_id, target_id)  # type: ignore[arg-type]
        t_info = introspect_table(session, target.table_name)
        ids = _owner_values(
            session,
            target,
            t_info,
            t_info.pk_column,
            lk,
            old,
            cap=MAX_LINKED + 1,  # type: ignore[arg-type]
        )
        if not ids:
            continue
        if rel.on_delete != "cascade" or new is None or len(ids) > MAX_LINKED:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"update restricted by relation '{rel.name}': changing '{key}' would "
                    "orphan related records"
                ),
            )
        for child_fid in ids:
            _cascade_rekey(session, user, target, str(child_fid), lk, new, rel, rls)


def _cascade_rekey(session, user, target: Collection, fid: str, lk: str, new, rel, rls) -> None:
    target = writable_collection(session, user, target.id)
    if not target.editable:
        raise HTTPException(status_code=403, detail="collection is not editable")
    info = introspect_table(session, target.table_name)
    q = lambda n: quote_ident(session, n)  # noqa: E731
    with rls(session, target.tenant_id):
        before = history.snapshot(features_repo.get_feature(session, info, fid=fid))
        r = session.execute(
            text(
                f"UPDATE public.{q(info.table_name)} SET {q(lk)} = :n "
                f"WHERE {q(info.pk_column)} = :f"
            ),
            {"n": new, "f": features_repo._coerce_fid(info, fid)},
        )
        after = history.snapshot(features_repo.get_feature(session, info, fid=fid))
    if r.rowcount != 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"cascade blocked by relation '{rel.name}': "
                "some related records are not updatable by you"
            ),
        )
    history.record_change(
        session,
        tenant_id=target.tenant_id,
        collection_id=target.id,
        fid=fid,
        op="update",
        before=before,
        after=after,
        actor_id=user.id,
    )
    write_audit(
        session,
        tenant_id=target.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="feature.update",
        object_type="feature",
        object_id=fid,
        payload={"collection": target.id, "fid": fid, "cascade": rel.id},
    )


def before_delete(session: Session, user, col: Collection, fid: str, rls, s3, *, depth: int = 0):
    """Politique de suppression (ADR 0021). restrict (défaut) : 409 si des enregistrements
    liés existent (comptés au rang propriétaire). cascade : les supprime, un à un, par la
    voie normale (can() write, RLS, journal ARC-15, audit), récursivement (profondeur 5)."""
    if depth > MAX_DEPTH:
        raise HTTPException(status_code=409, detail="relation cascade too deep")
    rels = relations_of(session, col.tenant_id, col.id)
    if not rels:  # chemin chaud (aucune relation) : pas d'introspection
        return
    info = introspect_table(session, col.table_name)
    for rel in rels:
        if rel.cardinality == "many_to_many":
            if col.id == rel.parent_collection_id:
                key, lk = rel.parent_key, rel.link_parent_key
            elif col.id == rel.child_collection_id:
                key, lk = rel.child_key, rel.link_child_key
            else:
                continue
            target_id = rel.link_collection_id
        elif col.id == rel.parent_collection_id:
            key, lk, target_id = rel.parent_key, rel.child_key, rel.child_collection_id
        else:
            continue
        value = _key_value(session, col, info, key, fid)
        if value is None:
            continue
        target = _same_tenant_collection(session, col.tenant_id, target_id)  # type: ignore[arg-type]
        t_info = introspect_table(session, target.table_name)
        ids = _owner_values(
            session,
            target,
            t_info,
            t_info.pk_column,
            lk,
            value,
            cap=MAX_LINKED + 1,  # type: ignore[arg-type]
        )
        if not ids:
            continue
        if rel.on_delete != "cascade":
            raise HTTPException(
                status_code=409,
                detail=f"delete restricted by relation '{rel.name}': related records exist",
            )
        if len(ids) > MAX_LINKED:
            raise HTTPException(status_code=409, detail="too many related records to cascade")
        for child_fid in ids:
            _cascade_delete(session, user, target, str(child_fid), rel, rls, s3, depth)


def _cascade_delete(session, user, target: Collection, fid: str, rel, rls, s3, depth: int):
    target = writable_collection(session, user, target.id)
    if not target.editable:
        raise HTTPException(status_code=403, detail="collection is not editable")
    before_delete(session, user, target, fid, rls, s3, depth=depth + 1)
    info = introspect_table(session, target.table_name)
    with rls(session, target.tenant_id):
        before = history.snapshot(features_repo.get_feature(session, info, fid=fid))
        ok = features_repo.delete_feature(session, info, fid=fid)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail=(
                f"cascade blocked by relation '{rel.name}': "
                "some related records are not deletable by you"
            ),
        )
    history.record_change(
        session,
        tenant_id=target.tenant_id,
        collection_id=target.id,
        fid=fid,
        op="delete",
        before=before,
        after=None,
        actor_id=user.id,
    )
    session.execute(
        text("UPDATE collections SET feature_count = feature_count - 1 WHERE id = :id"),
        {"id": target.id},
    )
    attachments_repo.delete_all_for_feature(
        session,
        s3,
        _attachments_bucket(),
        tenant_id=target.tenant_id,
        collection_id=target.id,
        fid=fid,
    )
    write_audit(
        session,
        tenant_id=target.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="feature.delete",
        object_type="feature",
        object_id=fid,
        payload={"collection": target.id, "fid": fid, "cascade": rel.id},
    )


def _attachments_bucket() -> str:
    from app.attachments.routes import get_attachments_bucket

    return get_attachments_bucket()


def restricting_relation(session: Session, col: Collection) -> str | None:
    """Nom d'une relation qui interdit un remplacement/vidage en masse de `col` (pipeline
    `replace`) : des enregistrements liés existent (rang propriétaire). Le cascade n'est
    jamais appliqué en masse : il reste réservé à la suppression unitaire."""
    q = lambda n: quote_ident(session, n)  # noqa: E731
    for rel in relations_of(session, col.tenant_id, col.id):
        if rel.cardinality == "many_to_many":
            if col.id not in (rel.parent_collection_id, rel.child_collection_id):
                continue
            target_id, key_col = rel.link_collection_id, None
        elif col.id == rel.parent_collection_id:
            target_id, key_col = rel.child_collection_id, rel.child_key
        else:
            continue
        target = _same_tenant_collection(session, col.tenant_id, target_id)  # type: ignore[arg-type]
        where = f" AND {q(key_col)} IS NOT NULL" if key_col else ""
        hit = session.execute(
            text(
                f"SELECT 1 FROM public.{q(target.table_name)} WHERE tenant_id = :t{where} LIMIT 1"
            ),
            {"t": col.tenant_id},
        ).first()
        if hit:
            return rel.name
    return None


class RelationHooks:
    """Branchée dans features.routes (injection, pas d'import vers le haut)."""

    def check_write(self, session, user, col, properties, fid, rls):
        check_write(session, user, col, properties, fid, rls)

    def before_update(self, session, user, col, fid, properties, rls):
        before_update(session, user, col, fid, properties, rls)

    def before_delete(self, session, user, col, fid, rls, s3):
        before_delete(session, user, col, fid, rls, s3)
