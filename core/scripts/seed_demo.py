"""Déclare les tables de démo comme collections éditables publiques.
Idempotent — utilisable à chaque démarrage d'environnement de démo.

Usage : DATABASE_URL=postgresql+psycopg://… uv run python -m scripts.seed_demo [--owner alice]
"""
import argparse
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collections.ddl import apply_collection_ddl
from app.collections.introspection import TableNotFound
from app.collections.introspection_pg import introspect_table
from app.collections.repository import create_collection, get_collection
from app.db import make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

DEMO_TABLES = {"incidents": "Incidents", "points_interet": "Points d'intérêt"}


def _owner(session: Session, tenant_id: str, username: str | None) -> User:
    if username:
        user = session.scalar(select(User).where(
            User.tenant_id == tenant_id, User.username == username))
        if user is None:
            raise SystemExit(f"owner '{username}' introuvable")
        return user
    admin = session.scalar(select(User).where(
        User.tenant_id == tenant_id, User.is_admin.is_(True)))
    if admin:
        return admin
    subs = [s.strip() for s in os.environ.get("CORE_ADMIN_SUBS", "").split(",") if s.strip()]
    if not subs:
        raise SystemExit("aucun admin : définir CORE_ADMIN_SUBS ou passer --owner")
    return get_or_create_user(session, tenant_id=tenant_id, oidc_sub=subs[0],
                              username=subs[0], email=None, first_name="", last_name="",
                              bootstrap_admin=True)


def seed(session: Session, owner_username: str | None = None) -> list[str]:
    tenant = get_or_create_default_tenant(session)
    owner = _owner(session, tenant.id, owner_username)
    created: list[str] = []
    for table, title in DEMO_TABLES.items():
        if get_collection(session, tenant_id=tenant.id, collection_id=table):
            continue
        try:
            info = introspect_table(session, table)
        except TableNotFound:
            print(f"table '{table}' absente — ignorée")
            continue
        apply_collection_ddl(session, table)
        create_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, table_name=table,
            title=title, description="Collection de démonstration", is_public=True,
            pk_column=info.pk_column, geometry_column=info.geometry_column,
            geometry_type=info.geometry_type, srid=info.srid,
        )
        created.append(table)
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default=None)
    args = parser.parse_args()
    engine = make_engine(os.environ["DATABASE_URL"])
    Session = make_session_factory(engine)
    with Session() as session:
        created = seed(session, owner_username=args.owner)
        session.commit()
    print(f"collections créées : {created or 'aucune (déjà en place)'}")


if __name__ == "__main__":
    main()
