# SPDX-License-Identifier: Apache-2.0
"""Kit de collecte (L8, AUD-004) : tout ce dont un formulaire hors-ligne a besoin pour saisir
et valider localement, en un seul document (schéma, domaines avec libellés, règles CEL,
champs de pièces jointes typés, géométrie, `required`). Aucune donnée de la collection.

Une seule construction pour les deux jumelles (kit privé, kit public) : le masquage GAP-22 est
appliqué ICI, jamais dans les routes (piège n°14). Le kit public ne révèle en plus ni nom de
table, ni identifiant de collection, ni champ sensible, ni pièce jointe sensible."""

import dataclasses
import hashlib
import json

from sqlalchemy.orm import Session

from app.collections.domains import strip_hidden, strip_hidden_rules, with_attribute_rules
from app.collections.introspection import Introspector, hide_sensitive_columns
from app.collections.models import Collection
from app.collections.schema_json import table_info_to_schema

KIT_VERSION = 1


def build_kit(
    session: Session,
    col: Collection,
    introspect: Introspector,
    *,
    sees_sensitive: bool,
    public: bool,
) -> dict:
    info = with_attribute_rules(introspect(session, col.table_name), col)
    sees_sensitive = sees_sensitive and not public  # le public ne voit JAMAIS un champ sensible
    attachment_fields = list(col.attachment_fields or [])
    if not sees_sensitive:
        info = hide_sensitive_columns(info, col.sensitive_fields)
        domains, subtypes = strip_hidden(info.domains, info.subtypes, col.sensitive_fields)
        info = dataclasses.replace(
            info,
            domains=domains,
            subtypes=subtypes,
            rules=strip_hidden_rules(info.rules, col.sensitive_fields),
        )
        attachment_fields = [f for f in attachment_fields if not f.get("sensitive")]
    schema = table_info_to_schema(info, attachment_fields=attachment_fields)
    rules = [
        r
        for r in (info.rules or [])
        if r.get("kind") in ("constraint", "calculation")  # `batch` = contrôle différé serveur
    ]
    kit = {
        "version": KIT_VERSION,
        "title": col.title,
        "schema": schema,
        "rules": rules,
        "geometryRequired": bool(info.geometry_required and info.geometry_column),
        "updatedAt": col.updated_at.replace(tzinfo=None).isoformat() + "Z"
        if col.updated_at
        else None,
    }
    if public:
        schema.pop("collection", None)  # nom de table
        schema.pop("pk", None)
    else:
        kit["collectionId"] = col.id
    kit["etag"] = etag_of(kit)
    return kit


def etag_of(kit: dict) -> str:
    """ETag fort : condensat du contenu canonique (le champ `etag` lui-même exclu)."""
    body = {k: v for k, v in kit.items() if k != "etag"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def if_none_match_hits(header: str | None, etag: str) -> bool:
    if not header:
        return False
    return any(p.strip().strip('"') == etag or p.strip() == "*" for p in header.split(","))
