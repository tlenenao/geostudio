# SPDX-License-Identifier: Apache-2.0
"""Appartenance aux groupes alimentée par les claims OIDC (ARC-24, ADR 0022).

Additif : ajoute les groupes mappés présents dans le claim, retire seulement les
appartenances d'origine `claim` dont le claim a disparu. `manual` n'est jamais
touchée. Un groupe ne donne que du partage — jamais un rôle/privilège.
"""

import logging
import os
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.sharing.models import GroupClaimMapping, GroupMember

_log = logging.getLogger(__name__)
_MAX_VALUES = 500
_MAX_LEN = 256


def groups_claim_name() -> str:
    return os.environ.get("CORE_OIDC_GROUPS_CLAIM", "groups") or "groups"


def parse_claim_values(raw: Any) -> set[str] | None:
    """None = claim mal formé (la synchro est alors sautée, rien n'est retiré).
    Absent = ensemble vide (les appartenances `claim` sont retirées)."""
    if raw is None:
        return set()
    if not isinstance(raw, list):
        return None
    return {v for v in raw[:_MAX_VALUES] if isinstance(v, str) and 0 < len(v) <= _MAX_LEN}


def sync_claim_memberships(
    session: Session, *, tenant_id: str, user_id: str, claim_values: set[str]
) -> None:
    mappings = session.execute(
        select(GroupClaimMapping.group_id, GroupClaimMapping.claim_value).where(
            GroupClaimMapping.tenant_id == tenant_id
        )
    ).all()
    wanted = {g for g, v in mappings if v in claim_values}
    rows = {
        m.group_id: m
        for m in session.scalars(
            select(GroupMember).where(
                GroupMember.user_id == user_id, GroupMember.tenant_id == tenant_id
            )
        )
    }
    for gid in wanted - rows.keys():
        session.add(GroupMember(group_id=gid, user_id=user_id, tenant_id=tenant_id, origin="claim"))
    stale = [gid for gid, m in rows.items() if m.origin == "claim" and gid not in wanted]
    if stale:
        session.execute(
            delete(GroupMember).where(
                GroupMember.user_id == user_id,
                GroupMember.origin == "claim",
                GroupMember.group_id.in_(stale),
            )
        )
    session.flush()


def apply_from_token_claims(
    session: Session, *, tenant_id: str, user_id: str, claims: dict[str, Any]
) -> None:
    """Point d'entrée du chemin de connexion : ne lève JAMAIS (un défaut ici
    bloquerait tout le monde) — toute erreur est journalisée et ignorée."""
    try:
        values = parse_claim_values(claims.get(groups_claim_name()))
        if values is None:
            return
        with session.begin_nested():
            sync_claim_memberships(
                session, tenant_id=tenant_id, user_id=user_id, claim_values=values
            )
    except Exception:  # noqa: BLE001 - le login ne doit jamais échouer ici
        _log.warning("claim group sync failed", exc_info=True)
