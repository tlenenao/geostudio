# SPDX-License-Identifier: Apache-2.0
"""Scope d'exécution RLS (spec SP-3 §2/§5, décision tenant 2026-07-10).

Toute requête sur une table métier s'exécute sous le rôle NON-propriétaire
gis_rls, borné au tenant courant par le GUC transactionnel app.tenant_id
(set_config(..., true) — paramétré, jamais interpolé). Le RESET ROLE en
sortie est OBLIGATOIRE : audit_log et les tables du cœur ne sont pas
grantées à gis_rls, et la suite de la requête (write_audit) s'exécute dans
la même transaction. Seul l'échec du RESET ROLE sur transaction déjà avortée
(SQLSTATE 25P02) est avalé, pour laisser remonter l'erreur SQL d'origine.
Validé à travers PgBouncer pool=transaction par
scripts/spike_pgbouncer_rls.py."""
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


@contextmanager
def rls_scope(session: Session, tenant_id: str):
    session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id}
    )
    session.execute(text("SET LOCAL ROLE gis_rls"))
    try:
        yield
    finally:
        try:
            session.execute(text("RESET ROLE"))
        except DBAPIError as exc:
            # Seul cas légitime : transaction déjà avortée par une erreur SQL
            # dans le scope (25P02 in_failed_sql_transaction) — le RESET
            # échouerait et masquerait l'erreur d'origine ; le rollback
            # imminent rend le rôle de toute façon. Tout AUTRE échec du RESET
            # laisserait la session sous gis_rls : on le laisse remonter.
            if getattr(exc.orig, "sqlstate", None) != "25P02":
                raise
