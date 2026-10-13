# SPDX-License-Identifier: Apache-2.0
"""ARC-13 (critère 3) : import dans une collection existante, lignes hors domaine rejetées
dans le rapport (PostGIS réel)."""

import pytest
from sqlalchemy import text

from app.collections import repository as collections_repo
from app.db import Base, make_session_factory
from app.features.rls import rls_scope
from app.ingestion.importer import run_append, run_import
from app.ingestion.parsers import IngestionParseError
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

SEED = b"nom,etat,largeur,lat,lon\nPont,bon,5,48.8,2.3\n"
APPEND = (
    b"nom,etat,largeur,lat,lon,extra\n"
    b"A,bon,3,48.1,2.1,x\n"  # valide
    b"B,ruine,3,48.2,2.2,x\n"  # hors domaine (liste)
    b"C,moyen,99,48.3,2.3,x\n"  # hors domaine (plage)
    b"D,mauvais,10,48.4,2.4,x\n"  # valide
)


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def _seed(Session, tenant, user):
    with Session() as s:
        res = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="seed.csv",
            content=SEED,
            collection_title="Ponts",
            lat_field=None,
            lon_field=None,
        )
        col = collections_repo.get_collection(
            s, tenant_id=tenant.id, collection_id=res.collection_id
        )
        col.field_domains = {
            "etat": {"type": "list", "values": ["bon", "moyen", "mauvais"]},
            "largeur": {"type": "range", "min": 0, "max": 30},
        }
        s.commit()
        return res.collection_id


def test_append_rejects_out_of_domain_rows_in_report(env):
    Session, tenant, user = env
    cid = _seed(Session, tenant, user)
    with Session() as s:
        report = run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id=cid,
            filename="more.csv",
            content=APPEND,
            lat_field=None,
            lon_field=None,
        )
        s.commit()
    assert report["inserted"] == 2
    assert report["rejectedCount"] == 2
    assert [r["row"] for r in report["rejected"]] == [2, 3]  # numéro de ligne (1 = 1re donnée)
    assert report["rejected"][0]["errors"][0]["field"] == "etat"
    assert report["rejected"][1]["errors"][0]["code"] == "out_of_domain"
    assert report["ignoredColumns"] == ["extra"]
    with Session() as s:
        names = s.execute(text(f"SELECT nom FROM public.{cid} ORDER BY nom")).scalars().all()
    assert names == ["A", "D", "Pont"]  # aucune rétro-application : "Pont" intact


def test_append_to_unknown_collection_fails(env):
    Session, tenant, user = env
    with Session() as s, pytest.raises(IngestionParseError):
        run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id="nope",
            filename="x.csv",
            content=APPEND,
            lat_field=None,
            lon_field=None,
        )


def test_append_all_rows_visible_through_rls(env):
    Session, tenant, user = env
    cid = _seed(Session, tenant, user)
    with Session() as s:
        run_append(
            s,
            tenant_id=tenant.id,
            user=user,
            collection_id=cid,
            filename="more.csv",
            content=APPEND,
            lat_field=None,
            lon_field=None,
        )
        s.commit()
    with Session() as s, rls_scope(s, tenant.id):
        n = s.execute(text(f"SELECT count(*) FROM public.{cid}")).scalar()
    assert n == 3
