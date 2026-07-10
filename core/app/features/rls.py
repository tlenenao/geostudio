"""Scope d'exécution RLS (spec SP-3 §2/§5, décision tenant 2026-07-10).

Toute requête sur une table métier s'exécute sous le rôle NON-propriétaire
gis_rls, borné au tenant courant par le GUC transactionnel app.tenant_id
(set_config(..., true) — paramétré, jamais interpolé). Le RESET ROLE en
sortie est OBLIGATOIRE : audit_log et les tables du cœur ne sont pas
grantées à gis_rls, et la suite de la requête (write_audit) s'exécute dans
la même transaction. Validé à travers PgBouncer pool=transaction par
scripts/spike_pgbouncer_rls.py."""
from contextlib import contextmanager

from sqlalchemy import text
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
        except Exception:
            # Transaction déjà avortée (erreur SQL dans le scope) : le RESET
            # échouerait en InFailedSqlTransaction et MASQUERAIT l'erreur
            # d'origine (IntegrityError → 409, WITH CHECK → 4xx). Sans gravité :
            # SET LOCAL ROLE est transactionnel, le rollback imminent rend le
            # rôle de toute façon.
            pass
