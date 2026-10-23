# SPDX-License-Identifier: Apache-2.0
"""L8 : réimport d'un XLSForm sur une collection existante.

Additif seulement. Une colonne nouvelle est créée ; libellés, domaines, règles `xf-*`, champs média
et `geometryRequired` sont mis à jour ; un retypage ou une suppression de colonne est BLOQUÉ (jamais
appliqué, jamais de perte de donnée) et rapporté. L'App déjà générée n'est jamais touchée."""

from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.domains import check_domain_config, check_rules_config, with_attribute_rules
from app.collections.introspection import ColumnInfo
from app.collections.models import Collection
from app.collections.schemas import AttributeRule, EmptyCollectionColumn, FieldDomain
from app.sql_ident import quote_ident
from app.xlsform.parser import XlsFormPlan

_SCALAR = {
    "text": "string",
    "integer": "integer",
    "bigint": "integer",
    "double precision": "number",
    "boolean": "boolean",
    "date": "date",
    "timestamptz": "datetime",
}
_SYSTEM_COLUMNS = {"id", "tenant_id", "geom"}


def _geom(value: str | None) -> str | None:
    return str(value).lower().removeprefix("st_") if value else None


def _same_type(sql_type: str, col: ColumnInfo) -> bool:
    if sql_type.endswith("[]"):
        return col.type == "list" and col.list_item_type == _SCALAR.get(sql_type[:-2])
    return col.type == _SCALAR.get(sql_type)


def apply_reimport(
    session: Session, col: Collection, plan: XlsFormPlan, introspect: Callable
) -> tuple[dict, list[str]]:
    """Applique la part sûre du plan ; renvoie `(differences, problèmes de configuration)`.
    En cas de problème de configuration, rien n'est écrit sur `col` (l'appelant lève 422)."""
    info = introspect(session, col.table_name)
    existing = {c.name: c for c in info.columns}
    plan_cols = {c["name"]: c["sqlType"] for c in plan.columns}
    added: list[dict] = []
    changed: list[dict] = []
    blocked: list[dict] = []
    skip: set[str] = set()  # champs bloqués : ni domaine ni règle appliqués

    for name, sql_type in plan_cols.items():
        if name not in existing:
            added.append({"name": name, "detail": sql_type})
        elif not _same_type(sql_type, existing[name]):
            skip.add(name)
            blocked.append({"name": name, "detail": f"retypage vers {sql_type} refusé"})
    for name in existing:
        if name not in plan_cols and name not in _SYSTEM_COLUMNS and name != info.pk_column:
            blocked.append({"name": name, "detail": "absente du formulaire, conservée"})
    if _geom(plan.geometry_type) != _geom(info.geometry_type):
        blocked.append({"name": "geometry", "detail": "changement de type de géométrie refusé"})

    domains = dict(col.field_domains or {})
    for field_, dom in plan.field_domains.items():
        if field_ in skip:
            continue
        new = FieldDomain(**dom).model_dump(exclude_none=True)
        if domains.get(field_) != new:
            if field_ in domains:
                changed.append({"name": field_, "detail": "domaine ou libellés"})
            domains[field_] = new
    planned = [
        AttributeRule(**r).model_dump(exclude_none=True)
        for r in plan.attribute_rules
        if r["field"] not in skip
    ]
    planned_fields = {r["field"] for r in planned}
    old_rules = list(col.attribute_rules or [])
    kept = [
        r
        for r in old_rules
        if not (str(r.get("id", "")).startswith("xf-") and r.get("field") in planned_fields)
    ]
    rules = kept + planned
    old_xf = [r for r in old_rules if str(r.get("id", "")).startswith("xf-")]
    new_xf = [r for r in planned if r["id"].startswith("xf-")]
    if sorted(old_xf, key=lambda r: r["id"]) != sorted(new_xf, key=lambda r: r["id"]):
        for f in sorted({r["field"] for r in old_xf + new_xf} - skip):
            if [r for r in old_xf if r["field"] == f] != [r for r in new_xf if r["field"] == f]:
                if f not in {c["name"] for c in changed} and f not in {a["name"] for a in added}:
                    changed.append({"name": f, "detail": "règles"})
    attachments = {a["key"]: a for a in (col.attachment_fields or [])}
    for a in plan.attachment_fields:
        if attachments.get(a["key"]) != a:
            if a["key"] in attachments:
                changed.append({"name": a["key"], "detail": "champ média"})
            attachments[a["key"]] = a
    if plan.geometry_required != col.geometry_required:
        changed.append({"name": "geometry", "detail": "géométrie requise"})

    # Validation avant toute écriture : colonnes ajoutées visibles par la vérification.
    t = quote_ident(session, col.table_name)
    for a in added:
        validated = EmptyCollectionColumn(name=a["name"], sqlType=plan_cols[a["name"]])
        session.execute(
            text(
                f"ALTER TABLE public.{t} ADD COLUMN {quote_ident(session, validated.name)} "
                f"{validated.sqlType}"
            )
        )
    new_info = with_attribute_rules(introspect(session, col.table_name), col)
    problems = check_domain_config(new_info, domains, {}) + check_rules_config(new_info, rules)
    if problems:
        return {}, problems
    col.field_domains = domains
    col.attribute_rules = rules
    col.attachment_fields = list(attachments.values())
    col.geometry_required = plan.geometry_required
    session.flush()
    return {"added": added, "changed": changed, "blocked": blocked}, []
